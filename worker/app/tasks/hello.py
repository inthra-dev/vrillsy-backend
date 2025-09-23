from app.celery_app import celery_app

@celery_app.task(name="vrillsy.hello")
def hello():
    return "pong"
