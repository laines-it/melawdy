import hashlib
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import music_check as music
from backend.config import Settings


@pytest.fixture
def demo(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, music_check_enabled=True,
                        music_check_worker_token="worker-key-" + "x" * 40,
                        music_check_data_dir=str(tmp_path))
    monkeypatch.setattr(music, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(music.router)
    with TestClient(app) as client:
        yield client, settings


def upload(client, body=b"demo audio", name="example.mp3", **kwargs):
    return client.post("/api/v1/music-check/jobs", content=body,
                       headers={"X-File-Name": name, **kwargs})


def owner(job):
    return {"X-Music-Job-Token": job["access_token"]}


def operator(settings):
    return {"Authorization": "Bearer " + settings.music_check_worker_token}


def claim(client, settings, job):
    response = client.post(f"/api/v1/music-check/worker/jobs/{job['id']}/claim", headers=operator(settings))
    assert response.status_code == 200, response.text
    return {**operator(settings), "X-Claim-Token": response.json()["lease_token"]}


def result(body=b"demo audio", **changes):
    return dict(outcome="completed", catalog_size=2, query_sha256=hashlib.sha256(body).hexdigest(),
                query_duration_seconds=60, window_seconds=20, hop_seconds=5,
                checkpoint_sha256="a" * 64, configuration_sha256="b" * 64,
                repo_commit="c" * 40,
                matches=[dict(reference="Another song", distance=0.12, query_start=5, query_end=25,
                              reference_start=10, reference_end=30)], **changes)


def test_upload_claim_callback_and_private_read_survive_new_store(demo):
    client, settings = demo
    created = upload(client, name="%D0%9C%D1%83%D0%B7%D1%8B%D0%BA%D0%B0.mp3")
    assert created.status_code == 201
    job = created.json()
    assert job["filename"] == "Музыка.mp3"
    path = f"/api/v1/music-check/jobs/{job['id']}"
    assert client.get(path).status_code == 404
    assert client.get(path + "/audio").status_code == 404
    assert client.get(path + "/audio", headers=owner(job)).content == b"demo audio"
    assert client.post(f"/api/v1/music-check/worker/jobs/{job['id']}/claim").status_code == 401
    headers = claim(client, settings, job)
    assert client.post(f"/api/v1/music-check/worker/jobs/{job['id']}/claim", headers=operator(settings)).status_code == 409
    assert client.get(path, headers=owner(job)).json()["status"] == "processing"
    base = f"/api/v1/music-check/worker/jobs/{job['id']}"
    assert client.get(base + "/audio", headers=headers).content == b"demo audio"
    assert client.put(base + "/result", headers=headers, json=result()).status_code == 200
    done = client.get(path, headers=owner(job))
    assert done.headers["cache-control"] == "no-store"
    assert done.json()["status"] == "completed"
    assert done.json()["result"]["matches"][0]["reference"] == "Another song"
    assert "access_token" not in done.json()
    assert client.put(base + "/result", headers=headers, json=result()).status_code == 409
    assert client.post(base + "/claim", headers=operator(settings)).status_code == 409
    assert music.Store().read(job["id"], job["access_token"])["status"] == "completed"


def test_old_lease_cannot_download_or_overwrite_new_attempt(demo):
    client, settings = demo
    job = upload(client).json()
    old = claim(client, settings, job)
    store = music.Store()
    with store.connect() as conn:
        conn.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))
    new = claim(client, settings, job)
    base = f"/api/v1/music-check/worker/jobs/{job['id']}"
    assert client.get(base + "/audio", headers=old).status_code == 409
    assert client.put(base + "/result", headers=old, json=result()).status_code == 409
    assert client.put(base + "/result", headers=new, json=result()).status_code == 200


def test_wrong_audio_hash_and_invalid_ranges_are_rejected(demo):
    client, settings = demo
    job = upload(client).json()
    headers = claim(client, settings, job)
    url = f"/api/v1/music-check/worker/jobs/{job['id']}/result"
    assert client.put(url, headers=headers, json=result(body=b"another file")).status_code == 422
    bad = result()
    bad["matches"][0]["query_end"] = 500
    assert client.put(url, headers=headers, json=bad).status_code == 422
    bad = result()
    bad["matches"][0]["distance"] = -1
    assert client.put(url, headers=headers, json=bad).status_code == 422
    assert music.Store().read(job["id"], job["access_token"])["status"] == "processing"


def test_failed_attempt_can_be_retried(demo):
    client, settings = demo
    job = upload(client).json()
    headers = claim(client, settings, job)
    payload = result()
    payload.update(outcome="failed", matches=[], catalog_size=0, message="Не удалось прочитать аудио")
    url = f"/api/v1/music-check/worker/jobs/{job['id']}/result"
    assert client.put(url, headers=headers, json=payload).status_code == 200
    assert music.Store().read(job["id"], job["access_token"])["status"] == "failed"
    assert claim(client, settings, job)["X-Claim-Token"] != headers["X-Claim-Token"]


def test_expired_jobs_are_inaccessible_and_audio_is_cleaned(demo):
    client, settings = demo
    job = upload(client).json()
    store = music.Store()
    assert store.path(job["id"]).exists()
    with store.connect() as conn:
        conn.execute("UPDATE jobs SET expires=? WHERE id=?", (time.time() - 1, job["id"]))
    assert client.get(f"/api/v1/music-check/jobs/{job['id']}", headers=owner(job)).status_code == 410
    assert not store.path(job["id"]).exists()
    assert claim_without_assert(client, settings, job).status_code == 410


def claim_without_assert(client, settings, job):
    return client.post(f"/api/v1/music-check/worker/jobs/{job['id']}/claim", headers=operator(settings))


def test_disabled_and_unconfigured_demo_reject_new_uploads(demo):
    client, settings = demo
    settings.music_check_enabled = False
    assert upload(client).status_code == 503
    settings.music_check_enabled = True
    settings.music_check_worker_token = ""
    assert upload(client).status_code == 503


def test_upload_validation_quota_and_interrupted_upload_cleanup(demo):
    client, settings = demo
    assert upload(client, name="payload.html").status_code == 422
    assert upload(client, body=b"").status_code == 413
    assert upload(client, **{"Content-Length": str(33 * 1024**2)}).status_code == 413
    assert upload(client, **{"Content-Length": "3"}).status_code == 413
    assert not list(Path(settings.music_check_data_dir).glob("*.audio"))
    settings.music_check_max_jobs = 1
    assert upload(client).status_code == 201
    assert upload(client).status_code == 429


def test_notebooks_are_self_contained_and_do_not_poll_operator_jobs(demo):
    client, _ = demo
    response = client.get("/api/v1/music-check/notebook")
    assert response.status_code == 200
    notebook = response.json()
    source = "\n".join(cell["source"] for cell in notebook["cells"])
    assert "WORKER_TOKEN = getpass(" in source
    assert "while True" not in source
    assert "HELPER_SOURCE" in source
    assert "configuration_sha256" in source
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile(cell["source"], "colab-cell", "exec")
            assert cell["outputs"] == []
