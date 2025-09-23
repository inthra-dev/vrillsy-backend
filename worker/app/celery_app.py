import os
from celery import Celery
from kombu import Queue

BROKER = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", BROKER)

celery_app = Celery(
    "vrillsy",
    broker=BROKER,
    backend=BACKEND,
    include=["app.vrillsy"],  # załaduj nasz task
)

celery_app.conf.update(
    task_queues=[Queue("vrillsy")],
    task_default_queue="vrillsy",
    task_routes={"vrillsy.render_job": {"queue": "vrillsy"}},
    timezone="UTC",
    task_ignore_result=False,
    result_expires=3600,
)

__all__ = ["celery_app"]
