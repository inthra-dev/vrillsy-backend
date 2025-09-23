import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from celery import Celery

router = APIRouter()

def _celery() -> Celery:
    broker = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
    backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
    return Celery("vrillsy", broker=broker, backend=backend)

def _outputs_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "/outputs"))

@router.get("/status/{task_id}")
def status(task_id: str):
    app = _celery()
    res = app.AsyncResult(task_id)
    payload = {"state": res.state, "ready": res.ready()}
    if res.ready():
        try:
            payload["result"] = res.result  # expected: {'ok': True, 'output': '/outputs/..', ...}
        except Exception as e:
            payload["result_error"] = str(e)
    return payload

@router.get("/download/{job_id}")
def download(job_id: str):
    path = _outputs_dir() / f"{job_id}_final.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="file_not_found")
    return FileResponse(str(path), media_type="video/mp4", filename=f"{job_id}.mp4")

@router.get("/download_by_task/{task_id}")
def download_by_task(task_id: str):
    app = _celery()
    res = app.AsyncResult(task_id)
    if not res.ready() or not res.result or not isinstance(res.result, dict):
        raise HTTPException(status_code=404, detail="not_ready")
    out = res.result.get("output")
    if not out or not Path(out).exists():
        raise HTTPException(status_code=404, detail="file_not_found")
    return FileResponse(out, media_type="video/mp4", filename=Path(out).name)
