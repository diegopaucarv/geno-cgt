import os

import requests
from celery import Celery

app = Celery("nlp_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
TEI_URL = os.getenv("TEI_URL", "http://tei:8080")


@app.task
def generar_embedding(texto: str):
    response = requests.post(f"{TEI_URL}/embed", json={"inputs": texto})
    response.raise_for_status()
    return response.json()  # devuelve el vector
