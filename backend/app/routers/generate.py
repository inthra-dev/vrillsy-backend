import os, uuid, shutil
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from celery import Celery

router = APIRouter()

def _shared_dir() -> Path:
    return Path(os.getenv("SHARED_DIR", "/shared"))

def _outputs_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "/outputs"))

def _celery() -> Celery:
    broker = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
    backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
    return Celery("vrillsy", broker=broker, backend=backend)

def _save(upload: UploadFile, dst: Path) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dst.stat().st_size

@router.post("/generate")
async def generate(
    audio: UploadFile = File(...),
    videos: List[UploadFile] = File(...),
):
    if not videos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_videos")

    job_id = uuid.uuid4().hex
    job_dir = _shared_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # save audio
    a_name = f"audio_{audio.filename or 'track'}"
    a_path = job_dir / a_name
    if _save(audio, a_path) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio_empty")

    # save videos
    v_paths: List[str] = []
    for v in videos:
        v_name = f"video_{v.filename or 'clip.mp4'}"
        v_path = job_dir / v_name
        _save(v, v_path)
        v_paths.append(str(v_path))

    # enqueue task
    out_dir = str(_outputs_dir())
    res = _celery().send_task("vrillsy.render_job",
                              args=[job_id, str(a_path), v_paths, out_dir],
                              queue="vrillsy")

    return {"ok": True, "job_id": job_id, "task_id": res.id}
