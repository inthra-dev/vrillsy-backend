if __name__ == "__main__":
    from shared.tasks import celery_app
    celery_app.worker_main()
