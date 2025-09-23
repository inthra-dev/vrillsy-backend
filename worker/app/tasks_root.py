from .celery_app import celery_app

@celery_app.task(name="vrillsy.hello")
def hello(name: str) -> str:
    return f"hello {name}"
