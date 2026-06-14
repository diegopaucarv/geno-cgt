# backend/app/core/celery_app.py
import os

from celery import Celery

# Usar Redis como broker y backend (puede ser RabbitMQ)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "iqas_gt",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "workers.fast.tasks",
        "workers.heavy.tasks",
        "workers.nlp.tasks",
    ],
)

# Configuración opcional
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "workers.fast.tasks.*": {"queue": "fast"},
        "workers.heavy.tasks.*": {"queue": "heavy"},
        "workers.nlp.tasks.*": {"queue": "nlp"},
    },
    task_acks_late=True,  # Confirma después de ejecutar, no al recibir
    task_reject_on_worker_lost=True,
)
