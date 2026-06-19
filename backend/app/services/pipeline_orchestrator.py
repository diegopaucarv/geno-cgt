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
        "next_state": None,  # terminal
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
                "SELECT id, estado, metadatos FROM documentos WHERE proyecto_id = :pid"
            ),
            {"pid": project_id},
        ).fetchall()

        if not docs:
            return {"status": "no_docs", "message": "No hay documentos"}

        # Clean old processing states on force (allow re-trigger of Phase B)
        if force:
            self.db.execute(
                text(
                    "DELETE FROM processing_states WHERE entity_type = 'project' "
                    "AND entity_id = :pid"
                ),
                {"pid": str(project_id)},
            )
            self.db.commit()

        # Crear PipelineRun
        run = PipelineRun(
            project_id=project_id,
            status="running",
            triggered_by="user",
            summary={"total_docs": len(docs)},
        )
        self.db.add(run)
        self.db.flush()

        # Analizar cada doc y despachar
        dispatched_segment = 0
        dispatched_agents = 0
        skipped = 0
        task_ids = {"segment": [], "agents": []}

        for row in docs:
            doc_id = str(row[0])
            estado = row[1] or "crudo"
            metadatos = row[2] if isinstance(row[2], dict) else {}

            if force:
                # Forzar desde cero: limpiar y empezar
                self._reset_document(doc_id)
                task = self._dispatch("crudo", doc_id, project_id, metadatos, run)
                if task:
                    dispatched_segment += 1
                    task_ids["segment"].append(
                        {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                    )
                continue

            # Chequear estado real
            n_segs = self._count_segments(doc_id, self.db)
            n_codes = self._count_codes(doc_id, self.db)

            # Reset errored docs so they can be retried
            if estado == "error":
                self.db.execute(
                    text("UPDATE documentos SET estado = 'crudo' WHERE id = :did"),
                    {"did": doc_id},
                )
                self.db.flush()
                estado = "crudo"

            if n_segs == 0:
                # Necesita segmentación
                task = self._dispatch("crudo", doc_id, project_id, metadatos, run)
                if task:
                    dispatched_segment += 1
                    task_ids["segment"].append(
                        {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                    )
            elif n_codes == 0:
                # Ya tiene segmentos, necesita agentes
                task = self._dispatch("segmentado", doc_id, project_id, metadatos, run)
                if task:
                    dispatched_agents += 1
                    task_ids["agents"].append(
                        {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                    )
            else:
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
            texto = metadatos.get("texto_preprocesado") or metadatos.get(
                "texto_extraido", ""
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
