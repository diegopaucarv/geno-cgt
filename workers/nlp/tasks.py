import logging
import os
import sys

# Asegurar que /app está en el path para Celery workers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from celery import Celery
from config import (
    DATABASE_URL,
    REDIS_URL,
    SEGMENTATION_REINERT,
    SPACY_EXCLUDE,
    TEI_URL,
)

MODEL_ID = os.getenv("MODEL_ID", "thomasht86/voyage-4-nano-ONNX")
from contextual_enrichment import build_contextualized_text
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)


# ── Pipeline log streaming ──────────────────────


# ── Pipeline log streaming ──────────────────────


def _plog(project_id: str, message: str):
    """Push a log line to Redis. Works in Celery child processes."""
    try:
        import json as _j
        import os as _os
        import time as _t

        import redis as _r

        rr = _r.Redis.from_url(_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        rr.rpush(
            f"pipeline_logs:{project_id}", _j.dumps({"ts": _t.time(), "msg": message})
        )
        rr.expire(f"pipeline_logs:{project_id}", 3600)
    except Exception:
        pass


# Monkey-patch the logger to also push to Redis
import logging as _logging

_original_info = _logging.Logger.info
_original_debug = _logging.Logger.debug
_original_warning = _logging.Logger.warning
_original_error = _logging.Logger.error


class _RedisLogger:
    project_id = ""


def _make_patched(original, level):
    def patched(self, msg, *args, **kwargs):
        original(self, msg, *args, **kwargs)
        if _RedisLogger.project_id:
            try:
                formatted = msg % args if args else msg
                _plog(_RedisLogger.project_id, f"[{level}] {formatted}")
            except Exception:
                pass

    return patched


_logging.Logger.info = _make_patched(_original_info, "INFO")
_logging.Logger.debug = _make_patched(_original_debug, "DEBUG")
_logging.Logger.warning = _make_patched(_original_warning, "WARN")
_logging.Logger.error = _make_patched(_original_error, "ERROR")


def _pipeline_log_to(project_id: str):
    _RedisLogger.project_id = project_id
    _plog(project_id, f"Pipeline log activado para proyecto {project_id[:8]}...")


app = Celery(
    "nlp_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)
app.conf.update(
    task_queues=(Queue("nlp", Exchange("nlp", type="direct"), routing_key="nlp"),),
    task_reject_on_worker_lost=True,
)


@app.task(name="update_saturation")
def update_saturation_stub(proyecto_id: str):
    """Stub: saturation update is handled by the heavy worker.
    This task arrives on the NLP queue but should be ignored here."""
    logger.debug("update_saturation stub called for %s — ignoring", proyecto_id)
    return {"status": "ignored", "note": "handled by worker-heavy"}


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
        json={"input": [text_to_embed], "model": MODEL_ID},
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return {"embedding": data[0]["embedding"], "enriched": text_to_embed != texto}


import signal as _signal

from celery import Task as _CeleryTask


class AbortableTask(_CeleryTask):
    """Tarea Celery que puede ser abortada limpiamente."""

    def __init__(self):
        self._aborted = False
        self._original_sigterm = None

    def __call__(self, *args, **kwargs):
        self._original_sigterm = _signal.getsignal(_signal.SIGTERM)
        _signal.signal(_signal.SIGTERM, self._handle_sigterm)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            if self._original_sigterm:
                _signal.signal(_signal.SIGTERM, self._original_sigterm)

    def _handle_sigterm(self, signum, frame):
        self._aborted = True
        logger.warning("Task %s received SIGTERM", self.name)
        if self._original_sigterm:
            _signal.signal(_signal.SIGTERM, self._original_sigterm)
        raise Exception(f"Task {self.name} cancelled by SIGTERM")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Mark PipelineTask as failed so frontend can detect & abort pipeline."""
        try:
            import psycopg2 as _pg

            _db = DATABASE_URL.replace("postgresql+asyncpg", "postgresql").replace(
                "postgresql+psycopg2", "postgresql"
            )
            _c = _pg.connect(_db)
            _c.autocommit = True
            _cur = _c.cursor()
            _cur.execute(
                "UPDATE pipeline_tasks SET status = 'failed' "
                "WHERE celery_task_id = %s AND status != 'completed'",
                (task_id,),
            )
            _cur.close()
            _c.close()
        except Exception:
            pass


class TaskCancelledError(Exception):
    pass


@app.task(
    name="segmentar_documento",
    base=AbortableTask,
    bind=True,
)
def segmentar_documento(
    self,
    texto: str,
    max_tokens: int = 1024,
    doc_title: str = "",
    source_type: str = "",
    global_summary: str = "",
    documento_id: str = "",
    manual_mode: bool = False,
):
    """Segmenta y persiste en DB si se proporciona documento_id."""
    from segmentador import ProgressiveSegmenter

    # Look up project_id BEFORE segmenting so logs are streamed even on failure
    _proj_id = ""
    if documento_id:
        try:
            import psycopg2 as _pg

            _db = DATABASE_URL.replace("postgresql+asyncpg", "postgresql").replace(
                "postgresql+psycopg2", "postgresql"
            )
            _c = _pg.connect(_db)
            _c.autocommit = True
            _cur = _c.cursor()
            _cur.execute(
                "SELECT proyecto_id FROM documentos WHERE id = %s", (documento_id,)
            )
            _row = _cur.fetchone()
            if _row:
                _proj_id = str(_row[0])
            _cur.close()
            _c.close()
        except Exception:
            pass
        if _proj_id:
            _pipeline_log_to(_proj_id)
            logger.info("✂️ Segmentación iniciada — %s chars", len(texto))

    reinert = SEGMENTATION_REINERT
    segmenter = ProgressiveSegmenter(
        spacy_exclude=SPACY_EXCLUDE,
        tei_url=TEI_URL,
        reinert_micro=reinert,
    )

    if not texto or not texto.strip():
        logger.error("Segmentacion: texto vacio para doc=%s", documento_id)
        if documento_id and _proj_id:
            try:
                from agents.transitions import _to_error

                db_url_sa = DATABASE_URL.replace(
                    "postgresql+asyncpg", "postgresql"
                ).replace("postgresql+psycopg2", "postgresql")
                from sqlalchemy import create_engine
                from sqlalchemy.orm import Session as SASession

                engine = create_engine(db_url_sa)
                with SASession(engine) as s:
                    _to_error(s, documento_id)
            except Exception as _e:
                logger.error("Failed to mark doc as error: %s", _e)
        return {"num_segmentos": 0, "error": "empty_text"}

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
                        (
                            sid,
                            documento_id,
                            seg_text.strip(),
                            i + 1,
                            len(seg_text.split()),
                        ),
                    )
                conn.commit()

                # Compute embeddings via TEI (outside the insert loop)
                if TEI_URL and segment_ids:
                    try:
                        texts = [t for _, t, _ in segment_ids]
                        resp = requests.post(
                            f"{TEI_URL}/v1/embeddings",
                            json={"input": texts, "model": MODEL_ID},
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
                        logger.info(
                            "Embeddings: doc=%s, %d segmentos",
                            documento_id,
                            len(embeddings),
                        )
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

                # Transicionar: NLP terminó → despachar agentes (solo si no es manual)
                if _proj_id and not manual_mode:
                    try:
                        from agents.transitions import transition

                        db_url_sa = DATABASE_URL.replace(
                            "postgresql+asyncpg", "postgresql"
                        ).replace("postgresql+psycopg2", "postgresql")
                        from sqlalchemy import create_engine
                        from sqlalchemy.orm import Session as SASession

                        engine = create_engine(db_url_sa)
                        with SASession(engine) as s:
                            from sqlalchemy import text as stxt

                            transition(
                                s,
                                documento_id,
                                _proj_id,
                                "segmentado",
                                "segmentar_documento",
                                True,
                            )
                            s.execute(
                                stxt(
                                    "INSERT INTO document_stage_progress (documento_id, agent_id) "
                                    "VALUES (:did, 'segmentar_documento') ON CONFLICT DO NOTHING"
                                ),
                                {"did": documento_id},
                            )
                            s.commit()
                    except Exception as _e:
                        logger.warning("Transition failed: %s", _e)
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
                conn.close()
        except Exception as e:
            logger.error("Segmentacion DB fallo: %s", e)
            # Mark document as error so pipeline can detect & abort
            if documento_id:
                try:
                    db_url_sa = DATABASE_URL.replace(
                        "postgresql+asyncpg", "postgresql"
                    ).replace("postgresql+psycopg2", "postgresql")
                    from sqlalchemy import create_engine
                    from sqlalchemy.orm import Session as SASession

                    engine = create_engine(db_url_sa)
                    with SASession(engine) as s:
                        from agents.transitions import _to_error

                        _to_error(s, documento_id)
                except Exception as _e:
                    logger.error("Failed to mark doc as error: %s", _e)
            # After _to_error call, push error signal to Redis
            try:
                import json as _j
                import os as _os

                import redis as _r

                rr = _r.Redis.from_url(_os.getenv("REDIS_URL", "redis://redis:6379/0"))
                rr.set(
                    f"pipeline_error:{_proj_id}",
                    _j.dumps(
                        {
                            "document_id": documento_id,
                            "error": str(e),
                            "ts": __import__("time").time(),
                        }
                    ),
                    ex=3600,
                )
            except Exception:
                pass
            raise  # re-raise so Celery sees the failure

    return {
        "num_segmentos": len(segmentos),
        "inserted": bool(documento_id),
    }
