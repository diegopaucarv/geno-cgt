# backend/app/core/celery_app.py
import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "iqas_gt",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

from kombu import Exchange, Queue

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_queues=(
        Queue("heavy", Exchange("heavy", type="direct"), routing_key="heavy"),
        Queue("nlp", Exchange("nlp", type="direct"), routing_key="nlp"),
        Queue("fast", Exchange("fast", type="direct"), routing_key="fast"),
    ),
    task_default_queue="heavy",
    task_default_exchange="heavy",
    task_default_routing_key="heavy",
)
