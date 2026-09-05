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
    timezone="UTC",
    beat_schedule={
        "dispatch-outbox-every-second": {
            "task": "c.dispatch_outbox",
            "schedule": 1.0,
        },
    },
)

celery_app.autodiscover_tasks(
    ["c_backend"],
)
