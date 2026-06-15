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
    documento_id: str = "",
):
    """Segmenta y persiste en DB si se proporciona documento_id."""
    from segmentador import ProgressiveSegmenter

    reinert = os.getenv("SEGMENTATION_REINERT", "true").lower() in ("1", "true", "yes")
    segmenter = ProgressiveSegmenter(tei_url=TEI_URL, reinert_micro=reinert)
    segmentos = segmenter.segment_text(texto, max_tokens=max_tokens)

    if documento_id:
        try:
            import psycopg2, uuid as _uuid
            db_url = os.getenv("DATABASE_URL", "postgresql://app_user:strongpass@postgres:5432/gt-db")
            db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2").replace("postgresql+psycopg2", "postgresql")
            conn = psycopg2.connect(db_url)
            conn.autocommit = False
            try:
                cur = conn.cursor()
                cur.execute("UPDATE documentos SET estado = 'segmentando' WHERE id = %s", (documento_id,))
                for i, seg in enumerate(segmentos):
                    seg_text = seg if isinstance(seg, str) else seg.get("texto", str(seg))
                    cur.execute(
                        "INSERT INTO segmentos (id, documento_id, texto, posicion, conteo_tokens, es_anomalia) "
                        "VALUES (%s, %s, %s, %s, %s, false)",
                        (str(_uuid.uuid4()), documento_id, seg_text.strip(), i + 1, len(seg_text.split())),
                    )
                conn.commit()
                logger.info("Segmentacion DB: doc=%s, %d segmentos", documento_id, len(segmentos))
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
                conn.close()
        except Exception as e:
            logger.warning("Segmentacion DB fallo: %s", e)

    return {
        "num_segmentos": len(segmentos),
        "inserted": bool(documento_id),
    }