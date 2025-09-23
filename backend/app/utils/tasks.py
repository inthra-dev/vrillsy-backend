import os
from typing import List
from celery import Celery
from ..config import get_settings

_settings = get_settings()
celery_app = Celery("vrillsy",
    broker=_settings.CELERY_BROKER_URL,
    backend=_settings.CELERY_BACKEND_URL,
)

def enqueue_render_job(job_id: str, audio_path: str, video_paths: List[str], out_dir: str | None = None) -> str:
    out = out_dir or os.getenv("OUTPUT_DIR", "/outputs")
    res = celery_app.send_task("vrillsy.render_job",
                               args=[job_id, audio_path, video_paths, out],
                               queue="vrillsy")
    return res.id
