import io
import json
import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings
import app.config as config_mod
import app.utils.tasks as tasks_mod

@pytest.fixture(autouse=True)
def override_settings(tmp_path, monkeypatch):
    test_shared = tmp_path / "shared"
    test_shared.mkdir(parents=True, exist_ok=True)
    s = Settings(
        SHARED_DIR=str(test_shared),
        MAX_VIDEOS=20,
        MAX_TOTAL_UPLOAD_MB=2,  # nisko do testu payload_too_large
        ALLOWED_VIDEO_MIME=["video/mp4"],
        ALLOWED_AUDIO_MIME=["audio/mpeg"],
        CELERY_BROKER_URL="memory://",
        CELERY_BACKEND_URL="rpc://",
    )
    monkeypatch.setattr(config_mod, "get_settings", lambda: s)
    yield

@pytest.fixture(autouse=True)
def stub_enqueue(monkeypatch):
    monkeypatch.setattr(tasks_mod, "enqueue_render_job", lambda job_id: "task_dummy_123")
    yield

client = TestClient(app)

def _fake_mp4(bytes_len=100_000):
    return io.BytesIO(b"\x00" * bytes_len)

def _fake_mp3(bytes_len=50_000):
    return io.BytesIO(b"\x00" * bytes_len)

def test_generate_happy_path(tmp_path):
    files = [
        ("audio", ("a.mp3", _fake_mp3(), "audio/mpeg")),
        ("videos", ("v1.mp4", _fake_mp4(), "video/mp4")),
        ("videos", ("v2.mp4", _fake_mp4(), "video/mp4")),
    ]
    data = {"user_id": "u1", "email": "x@example.com", "params": json.dumps({"duration":10})}
    r = client.post("/generate", data=data, files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "job_id" in body and "task_id" in body
    # manifest zapisany
    shared = config_mod.get_settings().SHARED_DIR
    manifest = next(Path(shared).glob(f"{body['job_id']}/manifest.json"))
    assert manifest.exists()
    manifest_data = json.loads(manifest.read_text())
    assert manifest_data["user_id"] == "u1"
    assert len(manifest_data["files"]["videos"]) == 2

def test_too_many_files(tmp_path):
    files = [("audio", ("a.mp3", _fake_mp3(), "audio/mpeg"))]
    # 21 wideo > MAX_VIDEOS (20)
    for i in range(21):
        files.append(("videos", (f"v{i}.mp4", _fake_mp4(), "video/mp4")))
    data = {"user_id": "u1", "email": "x@example.com"}
    r = client.post("/generate", data=data, files=files)
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["error"] == "too_many_files"

def test_payload_too_large(tmp_path):
    # Ustawiono limit 2 MB (w fixture). Spróbujmy wrzucić ~3MB łącznie.
    big = 3 * 1024 * 1024
    files = [
        ("audio", ("a.mp3", _fake_mp3(bytes_len=big//2), "audio/mpeg")),
        ("videos", ("v1.mp4", _fake_mp4(bytes_len=big//2), "video/mp4")),
        ("videos", ("v2.mp4", _fake_mp4(bytes_len=big//2), "video/mp4")),
    ]
    data = {"user_id": "u1", "email": "x@example.com"}
    r = client.post("/generate", data=data, files=files)
    assert r.status_code == 413
    body = r.json()
    assert body["detail"]["error"] == "payload_too_large"

def test_mime_not_allowed(tmp_path):
    files = [
        ("audio", ("a.mp3", _fake_mp3(), "audio/mpeg")),
        ("videos", ("bad.txt", io.BytesIO(b"abc"), "text/plain")),  # niedozwolone
    ]
    data = {"user_id": "u1", "email": "x@example.com"}
    r = client.post("/generate", data=data, files=files)
    assert r.status_code == 415
    body = r.json()
    assert body["detail"]["error"] == "mime_not_allowed"
