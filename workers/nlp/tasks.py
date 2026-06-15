import logging
import os
import sys

# Asegurar que /app está en el path para Celery workers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from celery import Celery
from contextual_enrichment import build_contextualized_text

logger = logging.getLogger(__name__)

app = Celery(
    "nlp_tasks",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)
TEI_URL = os.getenv("TEI_URL", "http://tei:8080")


@app.task(name="generar_embedding")
def generar_embedding(
    texto: str,
    doc_title: str = "",
    source_type: str = "",
    previous_segment: str = "",
    global_summary: str = "",
):
    """
    Genera embedding para un segmento.
    Si se proporciona metadata, enriquece el texto antes de embeberlo.
    """
    if doc_title or previous_segment:
        enriched = build_contextualized_text(
            segment_text=texto,
            doc_title=doc_title,
            source_type=source_type,
            previous_segment=previous_segment,
            global_summary=global_summary,
        )
        text_to_embed = enriched
        logger.debug(
            "Embedding enriquecido: +%d chars de contexto", len(enriched) - len(texto)
        )
    else:
        text_to_embed = texto

    response = requests.post(
        f"{TEI_URL}/v1/embeddings",
        json={"input": [text_to_embed], "model": "voyageai/voyage-4-nano"},
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return {"embedding": data[0]["embedding"], "enriched": text_to_embed != texto}


@app.task(name="segmentar_documento")
def segmentar_documento(
    texto: str,
    max_tokens: int = 1024,
    doc_title: str = "",
    source_type: str = "",
    global_summary: str = "",
):
    """
    Segmenta un texto usando ProgressiveSegmenter.

    Si se proporciona metadata del documento, los embeddings de cada
    segmento se generan con enriquecimiento contextual (título, fuente,
    resumen, contexto previo) para mejorar la precisión polisemántica.
    """
    from segmentador import ProgressiveSegmenter

    reinert = os.getenv("SEGMENTATION_REINERT", "true").lower() in ("1", "true", "yes")
    segmenter = ProgressiveSegmenter(tei_url=TEI_URL, reinert_micro=reinert)
    segmentos = segmenter.segment_text(texto, max_tokens=max_tokens)

    enriched_segments = []
    prev_text = ""

    for seg in segmentos:
        seg_text = seg if isinstance(seg, str) else seg.get("texto", str(seg))

        if doc_title or global_summary:
            enriched_text = build_contextualized_text(
                segment_text=seg_text,
                doc_title=doc_title,
                source_type=source_type,
                global_summary=global_summary,
                previous_segment=prev_text,
            )
        else:
            enriched_text = seg_text

        prev_text = seg_text

        if isinstance(seg, dict):
            seg["enriched_text"] = enriched_text
        enriched_segments.append(enriched_text)

    return {
        "num_segmentos": len(segmentos),
        "segmentos": segmentos,
        "enriched": bool(doc_title or global_summary),
    }
