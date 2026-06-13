import os
import time

from celery import Celery

app = Celery("heavy_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))


@app.task
def tarea_pesada(documento_id: str):
    # Simula trabajo intensivo (en fase 1 solo un sleep)
    time.sleep(10)
    return {"documento_id": documento_id, "procesado": True}
