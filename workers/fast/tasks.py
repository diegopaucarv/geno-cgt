import os

from celery import Celery

app = Celery("fast_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))


@app.task(name="ejemplo_tarea_rapida")
def ejemplo_tarea_rapida(data: dict):
    print(f"Procesando tarea rápida: {data}")
    return {"status": "ok"}
