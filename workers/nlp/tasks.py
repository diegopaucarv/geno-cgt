import os

import requests
from celery import Celery

app = Celery("nlp_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
TEI_URL = os.getenv("TEI_URL", "http://tei:8080")


@app.task(name="generar_embedding")
def generar_embedding(texto: str):
    response = requests.post(
        f"{TEI_URL}/v1/embeddings",
        json={"input": [texto], "model": "voyageai/voyage-4-nano"},
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return {"embedding": data[0]["embedding"]}


@app.task(name="segmentar_documento")
def segmentar_documento(texto: str, max_tokens: int = 1024):
    """Segmenta un texto usando ProgressiveSegmenter (llama a TEI para embeddings)."""
    from segmentador import ProgressiveSegmenter

    segmenter = ProgressiveSegmenter(tei_url=TEI_URL)
    segmentos = segmenter.segment_text(texto, max_tokens=max_tokens)
    return {"num_segmentos": len(segmentos), "segmentos": segmentos}
