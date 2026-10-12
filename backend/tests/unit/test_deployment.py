"""Exercise the real SSH entrypoint with isolated fake infrastructure commands."""
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
REVISION = 'a' * 40


def bundle(revision=REVISION):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        manifests = []
        for image in ('api', 'web'):
            config = f'{image}.json'
            data = json.dumps({'config': {'Labels': {'org.opencontainers.image.revision': revision}}}).encode()
            info = tarfile.TarInfo(config)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
            manifests.append({'Config': config, 'RepoTags': [f'melawdy-{image}:{REVISION}'], 'Layers': []})
        data = json.dumps(manifests).encode()
        info = tarfile.TarInfo('manifest.json')
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


@pytest.fixture
def deployment(tmp_path):
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    root = tmp_path / 'vps'
    (root / 'k3s').mkdir(parents=True)
    (root / 'k3s/kustomization.yaml').write_text((ROOT / 'deploy/k3s/kustomization.yaml').read_text())
    executable = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
root = Path(os.environ['MELAWDY_DEPLOY_ROOT'])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'git':
    print(os.environ['MAIN_REVISION'] + '\\trefs/heads/main')
elif name == 'curl':
    print(json.dumps({'revision': os.environ['MAIN_REVISION']}) if args[-1].endswith('version.json') else '[]')
else:
    with (root/'commands.jsonl').open('a') as log:
        log.write(json.dumps(args)+'\\n')
    state_path = root/'images.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'api':'melawdy-api:old', 'web':'melawdy-web:old'}
    if args[0] == 'ctr':
        sys.stdin.buffer.read()
    elif args[3] == 'get':
        print(state[args[5]])
    elif args[3] == 'exec':
        print('database-backup')
    elif args[3] == 'set':
        image, value = args[6].split('=',1)
        state[image] = value
        state_path.write_text(json.dumps(state))
    elif args[3] == 'rollout' and os.environ.get('FAIL_ROLLOUT') == '1' and state['api'].endswith(os.environ['MAIN_REVISION']):
        sys.exit(1)
'''
    for name in ('git', 'k3s', 'curl'):
        path = binaries / name
        path.write_text(executable)
        path.chmod(0o755)
    env = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
           'MELAWDY_DEPLOY_ROOT': str(root), 'MAIN_REVISION': REVISION,
           'SSH_ORIGINAL_COMMAND': f'deploy {REVISION}'}

    def run(data=None, **overrides):
        return subprocess.run(['bash', str(ROOT / 'deploy/k3s/deploy-release.sh')],
                              input=bundle() if data is None else data, capture_output=True,
                              env={**env, **overrides}, timeout=15)
    return root, run


def test_deployment_records_tested_revision_and_keeps_backup(deployment):
    root, run = deployment
    result = run()
    assert result.returncode == 0, result.stderr.decode()
    assert (root / 'deployed-revision').read_text().strip() == REVISION
    assert json.loads((root / 'images.json').read_text()) == {
        'api': f'melawdy-api:{REVISION}', 'web': f'melawdy-web:{REVISION}',
    }
    assert len(list((root / 'backups').glob('*.dump'))) == 1
    assert (root / 'k3s/kustomization.yaml').read_text().count(REVISION) == 2
    assert not list((root / 'releases').iterdir())


def test_failed_rollout_restores_previous_images_without_marking_success(deployment):
    root, run = deployment
    result = run(FAIL_ROLLOUT='1')
    assert result.returncode != 0
    assert json.loads((root / 'images.json').read_text()) == {
        'api': 'melawdy-api:old', 'web': 'melawdy-web:old',
    }
    assert not (root / 'deployed-revision').exists()
    assert len(list((root / 'backups').glob('*.dump'))) == 1
    assert b'restoring the previous application images' in result.stderr
    assert not list((root / 'releases').iterdir())


def test_superseded_main_run_never_updates_the_application(deployment):
    root, run = deployment
    result = run(MAIN_REVISION='b' * 40)
    assert result.returncode == 0
    assert not (root / 'commands.jsonl').exists()
    assert not (root / 'deployed-revision').exists()
    assert b'Skipping superseded commit' in result.stdout


def test_mismatched_image_revision_is_rejected_before_database_or_cluster_changes(deployment):
    root, run = deployment
    result = run(data=bundle('b' * 40))
    assert result.returncode != 0
    assert not (root / 'commands.jsonl').exists()
    assert not list((root / 'backups').iterdir())


def test_deploy_key_cannot_execute_arbitrary_ssh_commands(deployment):
    root, run = deployment
    result = run(SSH_ORIGINAL_COMMAND='bash -c whoami')
    assert result.returncode == 64
    assert not (root / 'commands.jsonl').exists()
