import os

from celery import Celery

celery_app = Celery(
    "proyecto",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)

celery_app.conf.update(
    task_routes={
        "fast_tasks.*": {"queue": "fast"},
        "nlp_tasks.*": {"queue": "nlp"},
        "heavy_tasks.*": {"queue": "heavy"},
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
