from c_backend.celery_app import celery_app


@celery_app.task(name="c.process_test_message")
def process_test_message(message: str) -> str:
    print(f"C worker received: {message}")
    return f"processed: {message}"
