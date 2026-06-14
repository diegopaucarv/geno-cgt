import os
import time

from celery import Celery

app = Celery("heavy_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))


@app.task(name="tarea_pesada")
def tarea_pesada(documento_id: str):
    time.sleep(10)
    return {"documento_id": documento_id, "procesado": True}
