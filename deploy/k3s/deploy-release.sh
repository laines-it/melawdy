#!/usr/bin/env bash
# Installed as a forced-command entrypoint for the GitHub Actions SSH key.
set -Eeuo pipefail
umask 077

read -r operation revision extra <<< "${SSH_ORIGINAL_COMMAND:-}"
if [[ "$operation" != deploy || ! "$revision" =~ ^[0-9a-f]{40}$ || -n "${extra:-}" ]]; then
    echo 'Expected: deploy <40-character commit SHA>' >&2
    exit 64
fi

root=${MELAWDY_DEPLOY_ROOT:-/opt/melawdy}
mkdir -p "$root/releases"
exec 9>"$root/deploy.lock"
flock -w 900 9
release_dir=$(mktemp -d "$root/releases/upload-XXXXXXXX")
cleanup() { rm -rf -- "$release_dir"; }
trap cleanup EXIT
# Limit the upload to 1 GiB; receive it completely before touching the live app.
echo 'Receiving release images (upload timeout: 900 seconds)'
if (ulimit -f 1048576; timeout 900 cat > "$release_dir/images.tar.gz"); then
    echo "Upload complete: $(wc -c < "$release_dir/images.tar.gz") bytes"
else
    status=$?
    echo "Release upload failed (exit $status); application images have not been changed" >&2
    exit "$status"
fi
python3 - "$release_dir/images.tar.gz" "$revision" <<'PY'
import json
import sys
import tarfile

archive, revision = sys.argv[1:]
expected = {f'melawdy-api:{revision}', f'melawdy-web:{revision}'}
with tarfile.open(archive, 'r:gz') as bundle:
    manifests = json.load(bundle.extractfile('manifest.json'))
    tags = [tag.removeprefix('docker.io/library/') for image in manifests for tag in image.get('RepoTags', [])]
    if len(manifests) != 2 or len(tags) != 2 or set(tags) != expected:
        raise SystemExit('Archive must contain only the two MeLawDy release images')
    for image in manifests:
        config = json.load(bundle.extractfile(image['Config']))
        if config.get('config', {}).get('Labels', {}).get('org.opencontainers.image.revision') != revision:
            raise SystemExit('Image revision label does not match the requested commit')
PY

# A slow older CI run must never replace a newer main revision.
main_revision=$(timeout 30 git ls-remote https://github.com/laines-it/melawdy.git refs/heads/main | cut -f1)
if [[ "$main_revision" != "$revision" ]]; then
    echo "Skipping superseded commit $revision; main is $main_revision"
    exit 0
fi

kube() { k3s kubectl -n melawdy "$@"; }
old_api=$(kube get deployment api -o 'jsonpath={.spec.template.spec.containers[0].image}')
old_web=$(kube get deployment web -o 'jsonpath={.spec.template.spec.containers[0].image}')
new_api="melawdy-api:$revision"
new_web="melawdy-web:$revision"

gzip -dc "$release_dir/images.tar.gz" | k3s ctr images import -

rollback() {
    status=$?
    trap - ERR
    echo 'Deployment failed; restoring the previous application images' >&2
    kube set image deployment/api "api=$old_api" || true
    kube set image deployment/web "web=$old_web" || true
    kube rollout status deployment/api --timeout=180s || true
    kube rollout status deployment/web --timeout=180s || true
    echo 'Database migrations are not downgraded automatically' >&2
    exit "$status"
}
trap rollback ERR
kube set image deployment/api "api=$new_api"
kube set image deployment/web "web=$new_web"
kube rollout status deployment/api --timeout=180s
kube rollout status deployment/web --timeout=180s
curl --fail --silent --show-error --retry 5 --retry-delay 2 --max-time 15 \
    --resolve lawmposer.ru:443:127.0.0.1 https://lawmposer.ru/api/v1/public/articles > /dev/null
curl --fail --silent --show-error --retry 5 --retry-delay 2 --max-time 15 \
    --resolve lawmposer.ru:443:127.0.0.1 https://lawmposer.ru/version.json \
    | python3 -c 'import json,sys; assert json.load(sys.stdin)["revision"] == sys.argv[1]' "$revision"

trap - ERR
kube annotate deployment api web "melawdy.ru/revision=$revision" --overwrite
printf '%s\n' "$revision" > "$root/deployed-revision.tmp"
mv "$root/deployed-revision.tmp" "$root/deployed-revision"
# Keep the manual manifests aligned with the running application images.
python3 - "$root/k3s/kustomization.yaml" "$revision" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
for image in ('melawdy-api', 'melawdy-web'):
    text, count = re.subn(r'(- name: ' + image + r'\n\s+newTag:) [^\n]+', r'\g<1> "' + sys.argv[2] + '"', text)
    if count != 1:
        raise SystemExit(f'Expected exactly one image entry for {image}')
path.write_text(text)
PY
echo "Deployed main@$revision"
