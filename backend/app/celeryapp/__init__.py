from celery import Celery
from ..config import get_settings
s = get_settings()
celery_app = Celery(
    "vrillsy",
    broker=s.CELERY_BROKER_URL,
    backend=s.CELERY_BACKEND_URL,
)
celery_app.conf.update(
    imports=["worker.tasks.render_job"],  # <- najważniejsze
    task_default_queue="celery",
)
