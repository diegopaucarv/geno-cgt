import logging
import os
import sys

# Asegurar que /app está en el path para Celery workers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from celery import Celery
from config import DATABASE_URL, REDIS_URL, SEGMENTATION_REINERT, TEI_URL
from contextual_enrichment import build_contextualized_text

logger = logging.getLogger(__name__)

app = Celery(
    "nlp_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)


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

    reinert = SEGMENTATION_REINERT
    segmenter = ProgressiveSegmenter(tei_url=TEI_URL, reinert_micro=reinert)
    segmentos = segmenter.segment_text(texto, max_tokens=max_tokens)

    if documento_id:
        try:
            import uuid as _uuid

            import psycopg2

            db_url = DATABASE_URL
            db_url = db_url.replace(
                "postgresql+asyncpg", "postgresql+psycopg2"
            ).replace("postgresql+psycopg2", "postgresql")
            conn = psycopg2.connect(db_url)
            conn.autocommit = False
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE documentos SET estado = 'segmentando' WHERE id = %s",
                    (documento_id,),
                )
                # Eliminar segmentos previos para evitar duplicados
                cur.execute(
                    "DELETE FROM segmentos WHERE documento_id = %s",
                    (documento_id,),
                )
                segment_ids = []
                for i, seg in enumerate(segmentos):
                    seg_text = (
                        seg if isinstance(seg, str) else seg.get("texto", str(seg))
                    )
                    sid = str(_uuid.uuid4())
                    segment_ids.append((sid, seg_text.strip(), i))
                    cur.execute(
                        "INSERT INTO segmentos (id, documento_id, texto, posicion, conteo_tokens, es_anomalia) "
                        "VALUES (%s, %s, %s, %s, %s, false)",
                        (sid, documento_id, seg_text.strip(), i + 1, len(seg_text.split())),
                    )
                conn.commit()

                # Compute embeddings via TEI (outside the insert loop)
                if TEI_URL and segment_ids:
                    try:
                        texts = [t for _, t, _ in segment_ids]
                        resp = requests.post(
                            f"{TEI_URL}/v1/embeddings",
                            json={"input": texts, "model": "voyageai/voyage-4-nano"},
                            timeout=120.0,
                        )
                        resp.raise_for_status()
                        embeddings = [d["embedding"] for d in resp.json()["data"]]
                        for (sid, _, _), emb in zip(segment_ids, embeddings):
                            cur.execute(
                                "UPDATE segmentos SET embedding = %s WHERE id = %s",
                                (emb, sid),
                            )
                        conn.commit()
                        logger.info("Embeddings: doc=%s, %d segmentos", documento_id, len(embeddings))
                    except Exception as ee:
                        logger.warning("Embedding fallo (non-fatal): %s", ee)
                        conn.rollback()

                # Marcar como segmentado
                cur.execute(
                    "UPDATE documentos SET estado = 'segmentado' WHERE id = %s",
                    (documento_id,),
                )
                conn.commit()
                logger.info(
                    "Segmentacion DB: doc=%s, %d segmentos",
                    documento_id,
                    len(segmentos),
                )
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
