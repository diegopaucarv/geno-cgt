"""Pipeline Orchestrator — Centralized state machine for document processing.

SOLO este módulo puede:
- Cambiar el estado de un documento
- Despachar la siguiente tarea
- Crear tracking (PipelineTask)
- Disparar Phase B (con deduplicación)

Los workers NUNCA despachan otras tareas. Solo reportan su resultado
y el orchestrator decide el siguiente paso.

Race conditions eliminadas vía optimistic locking (UPDATE ... WHERE estado = from_state).
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.models.domain.pipeline_run import PipelineRun, PipelineTask
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# State machine
# ═══════════════════════════════════════════════════════════════════════

# Document states and what to dispatch next
TRANSITIONS: dict[str, dict] = {
    "crudo": {
        "next_state": "segmentando",
        "task_name": "segmentar_documento",
        "queue": "nlp",
    },
    "preprocesando": {
        "next_state": "preprocesado",
        "task_name": None,  # worker updates estado directly
        "queue": None,
    },
    "preprocesado": {
        "next_state": "segmentando",
        "task_name": "segmentar_documento",
        "queue": "nlp",
    },
    "segmentando": {
        "next_state": "segmentado",
        "task_name": None,  # NLP worker updates estado directly
        "queue": None,
    },
    "segmentado": {
        "next_state": "procesando",
        "task_name": "process_document_agents_a",
        "queue": "heavy",
    },
    "procesando": {
        "next_state": "listo",
        "task_name": None,  # heavy worker updates estado directly
        "queue": None,
    },
    "listo": {
        "next_state": None,  # terminal (open coding completado)
        "task_name": None,
        "queue": None,
    },
    "resumiendo": {
        "next_state": "resumido",
        "task_name": None,  # worker updates estado directly
        "queue": None,
    },
    "resumido": {
        "next_state": None,  # terminal (incident summaries done)
        "task_name": None,
        "queue": None,
    },
    "error": {
        "next_state": "crudo",  # reset on retry
        "task_name": None,
        "queue": None,
    },
}


class PipelineOrchestrator:
    """Centralized dispatcher. Único punto que despacha tareas."""

    def __init__(self, db_session: Session):
        self.db = db_session

    # ═══════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════

    def start_pipeline(self, project_id: UUID, force: bool = False) -> dict:
        """Entry point: analiza el proyecto y despacha las tareas iniciales.

        Called by POST /pipeline/run
        """
        from app.models.domain.document import Documento
        from app.models.domain.project import Proyecto

        # Verificar proyecto
        proyecto = self.db.get(Proyecto, project_id)
        if not proyecto:
            return {"status": "error", "message": "Proyecto no encontrado"}

        # Obtener docs
        docs = self.db.execute(
            text(
                "SELECT id, estado, metadatos FROM documentos WHERE proyecto_id = :pid ORDER BY sort_order"
            ),
            {"pid": project_id},
        ).fetchall()

        if not docs:
            return {"status": "no_docs", "message": "No hay documentos"}

        # ── 0. Check for fatal errors before dispatching anything ──
        pid_str = str(project_id)
        fatal_error = self._check_fatal_error(pid_str)
        if fatal_error:
            return {
                "status": "error",
                "message": f"Pipeline blocked: fatal error on document {fatal_error.get('document_id', 'unknown')[:8]}... — {fatal_error.get('error', 'unknown error')}",
                "fatal_error": fatal_error,
            }

        # Clean old processing states AND error signals on force
        if force:
            self.db.execute(
                text(
                    "DELETE FROM processing_states WHERE entity_type = 'project' "
                    "AND entity_id = :pid"
                ),
                {"pid": pid_str},
            )
            self.db.commit()
            # Clear any fatal error signal from Redis
            try:
                import os as _os2

                import redis as _r2

                rr = _r2.Redis.from_url(
                    _os2.getenv("REDIS_URL", "redis://redis:6379/0")
                )
                rr.delete(f"pipeline_error:{pid_str}")
            except Exception:
                pass

        # Crear PipelineRun
        run = PipelineRun(
            project_id=project_id,
            status="running",
            triggered_by="user",
            summary={"total_docs": len(docs)},
        )
        self.db.add(run)
        self.db.flush()

        # Dispatch ONE segment and ONE agents task at a time.
        # The transition chain handles subsequent docs sequentially.
        dispatched_segment = 0
        dispatched_agents = 0
        skipped = 0
        task_ids = {"segment": [], "agents": []}

        if force:
            # Forzar desde cero: reset all, but dispatch only the FIRST doc
            first_doc = None
            for row in docs:
                doc_id = str(row[0])
                self._reset_document(doc_id)
                if first_doc is None:
                    raw_meta = row[2]
                    if isinstance(raw_meta, dict):
                        meta = raw_meta
                    elif isinstance(raw_meta, str):
                        try:
                            meta = __import__("json").loads(raw_meta)
                        except Exception:
                            meta = {}
                    else:
                        meta = {}
                    first_doc = (doc_id, meta)

            if first_doc:
                doc_id, metadatos = first_doc
                task = self._dispatch("crudo", doc_id, project_id, metadatos, run)
                if task:
                    dispatched_segment += 1
                    task_ids["segment"].append(
                        {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                    )
                skipped = len(docs) - 1
        else:
            # Find first doc needing segment and first doc needing agents.
            # Only ONE of each type at a time.
            for row in docs:
                doc_id = str(row[0])
                estado = row[1] or "crudo"
                raw_meta = row[2]
                if isinstance(raw_meta, dict):
                    metadatos = raw_meta
                elif isinstance(raw_meta, str):
                    try:
                        metadatos = __import__("json").loads(raw_meta)
                    except Exception:
                        metadatos = {}
                else:
                    metadatos = {}

                # Reset errored docs so they can be retried
                if estado == "error":
                    self.db.execute(
                        text("UPDATE documentos SET estado = 'crudo' WHERE id = :did"),
                        {"did": doc_id},
                    )
                    self.db.flush()
                    estado = "crudo"

                n_segs = self._count_segments(doc_id, self.db)
                n_codes = self._count_codes(doc_id, self.db)

                if n_segs == 0 and dispatched_segment == 0:
                    # First doc needing segmentation (crudo or preprocesado)
                    from_state = "crudo"
                    if estado == "preprocesado":
                        from_state = "preprocesado"
                    task = self._dispatch(
                        from_state, doc_id, project_id, metadatos, run
                    )
                    if task:
                        dispatched_segment += 1
                        task_ids["segment"].append(
                            {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                        )
                elif n_segs > 0 and n_codes == 0 and dispatched_agents == 0:
                    # First doc needing agents
                    task = self._dispatch(
                        "segmentado", doc_id, project_id, metadatos, run
                    )
                    if task:
                        dispatched_agents += 1
                        task_ids["agents"].append(
                            {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                        )
                elif n_segs > 0 and n_codes > 0:
                    skipped += 1

        run.summary = {
            "total_docs": len(docs),
            "need_segment": dispatched_segment,
            "need_agents": dispatched_agents,
            "already_done": skipped,
        }
        self.db.commit()

        # If all docs already done, trigger Phase B directly (no transition will fire it)
        if skipped == len(docs) and skipped >= 3:
            from app.agents.transitions import _maybe_trigger_phase_b

            result = _maybe_trigger_phase_b(self.db, str(project_id))
            if result:
                task_ids["phase_b"] = result.get("task_id")

        return {
            "status": "dispatched",
            "project_id": str(project_id),
            "run_id": str(run.id),
            "summary": run.summary,
            "task_ids": task_ids,
        }

    # ═══════════════════════════════════════════════════════════════
    # Internal
    # ═══════════════════════════════════════════════════════════════

    def _reset_document(self, doc_id: str):
        """Resetea un documento a estado crudo (para force=True)."""
        self.db.execute(
            text("DELETE FROM segmentos WHERE documento_id = :did"),
            {"did": doc_id},
        )
        self.db.execute(
            text(
                "DELETE FROM codigos_segmento WHERE segmento_id IN "
                "(SELECT id FROM segmentos WHERE documento_id = :did)"
            ),
            {"did": doc_id},
        )
        self.db.execute(
            text("UPDATE documentos SET estado = 'crudo' WHERE id = :did"),
            {"did": doc_id},
        )
        self.db.commit()

    def _dispatch(
        self,
        from_state: str,
        doc_id: str,
        project_id: UUID,
        metadatos: dict,
        run: PipelineRun,
    ) -> dict | None:
        """Despacha la siguiente tarea según TRANSITIONS y crea PipelineTask."""
        trans = TRANSITIONS.get(from_state)
        if not trans or not trans["task_name"]:
            return None

        # Update document estado (optimistic locking)
        self.db.execute(
            text(
                "UPDATE documentos SET estado = :next "
                "WHERE id = :did AND estado = :from_st"
            ),
            {"next": trans["next_state"], "did": doc_id, "from_st": from_state},
        )
        self.db.flush()

        # Dispatch Celery task via shared app instance
        if trans["task_name"] == "segmentar_documento":
            # Priority: classified (baseline_data XML tags) → preprocessed → extracted → original
            texto = (
                metadatos.get("texto_clasificado")
                or metadatos.get("texto_preprocesado")
                or metadatos.get("texto_extraido", "")
                or metadatos.get("texto_original", "")
            )
            task = celery_app.send_task(
                trans["task_name"],
                args=[texto, 1024, "", "TEXTO", "", doc_id],
                queue=trans["queue"],
            )
        else:
            task = celery_app.send_task(
                trans["task_name"],
                args=[doc_id, str(project_id)],
                queue=trans["queue"],
            )

        # Create PipelineTask tracking
        self.db.execute(
            text(
                "INSERT INTO pipeline_tasks "
                "(id, run_id, document_id, celery_task_id, task_name, queue, status, doc_estado_before, segments_before, codes_before) "
                "VALUES (gen_random_uuid(), :rid, :did, :tid, :tn, :q, 'queued', :before, 0, 0)"
            ),
            {
                "rid": run.id,
                "did": doc_id,
                "tid": task.id,
                "tn": trans["task_name"],
                "q": trans["queue"],
                "before": from_state,
            },
        )
        self.db.flush()

        return {
            "celery_task_id": task.id,
            "doc_id": doc_id,
            "task_name": trans["task_name"],
            "queue": trans["queue"],
        }

    @staticmethod
    def _count_segments(doc_id: str, session=None) -> int:
        """Cuenta segmentos. Usa la sesión pasada o crea una nueva."""
        if session is not None:
            return session.execute(
                text("SELECT COUNT(*) FROM segmentos WHERE documento_id = :did"),
                {"did": doc_id},
            ).fetchone()[0]
        import os as _os

        from sqlalchemy import create_engine

        url = _os.getenv("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        engine = create_engine(url)
        from sqlalchemy.orm import Session as SyncSession

        with SyncSession(engine) as s:
            return s.execute(
                text("SELECT COUNT(*) FROM segmentos WHERE documento_id = :did"),
                {"did": doc_id},
            ).fetchone()[0]

    @staticmethod
    def _count_codes(doc_id: str, session=None) -> int:
        """Cuenta códigos. Usa la sesión pasada o crea una nueva."""
        if session is not None:
            return session.execute(
                text(
                    "SELECT COUNT(cs.segmento_id) FROM segmentos s "
                    "JOIN codigos_segmento cs ON cs.segmento_id = s.id "
                    "WHERE s.documento_id = :did"
                ),
                {"did": doc_id},
            ).fetchone()[0]
        import os as _os

        from sqlalchemy import create_engine

        url = _os.getenv("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        engine = create_engine(url)
        from sqlalchemy.orm import Session as SyncSession

        with SyncSession(engine) as s:
            return s.execute(
                text(
                    "SELECT COUNT(cs.segmento_id) FROM segmentos s "
                    "JOIN codigos_segmento cs ON cs.segmento_id = s.id "
                    "WHERE s.documento_id = :did"
                ),
                {"did": doc_id},
            ).fetchone()[0]

    @staticmethod
    def _check_fatal_error(project_id: str) -> dict | None:
        """Check Redis for fatal error signals from workers.

        Called before dispatching any new task. If a segmentation
        or preprocessing worker reported a fatal error, the pipeline
        is blocked until the researcher clears the error.

        Returns:
            dict with error details if found, None if pipeline is clear.
        """
        try:
            import json as _j
            import os as _os

            import redis as _r

            rr = _r.Redis.from_url(_os.getenv("REDIS_URL", "redis://redis:6379/0"))
            raw = rr.get(f"pipeline_error:{project_id}")
            if raw:
                return _j.loads(raw)
        except Exception:
            pass
        return None
