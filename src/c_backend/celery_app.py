from celery import Celery

from c_backend.config import get_settings


settings = get_settings()

celery_app = Celery(
    "c",
    broker=settings.celery_broker_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

celery_app.autodiscover_tasks(
    ["c_backend"],
)
