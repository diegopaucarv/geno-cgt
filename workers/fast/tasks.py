import os

from celery import Celery

app = Celery("fast_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))


@app.task
def ejemplo_tarea_rapida(data: dict):
    # Aquí irá la lógica ligera (ej. validar un JSON, enviar un email)
    print(f"Procesando tarea rápida: {data}")
    return {"status": "ok"}
