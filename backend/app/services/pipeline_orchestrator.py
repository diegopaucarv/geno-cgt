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

# Document states and what to dispatch next.
# Espeja app/agents/transitions.py::NEXT para la escalera classify-first:
#   crudo|preprocesado → clasificando → clasificado
#                      → segmentando → segmentado
#                      → procesando → extrayendo → incidentes_extraidos
# _dispatch consulta _resolve_next, que es la fuente de verdad y además degrada
# el segmentador a `segmentar_documento_llm` cuando no hay worker-nlp; esta
# tabla queda como respaldo legible para los estados legacy.
TRANSITIONS: dict[str, dict] = {
    "crudo": {
        "next_state": "clasificando",
        "task_name": "run_glaser_classifier",
        "queue": "heavy",
    },
    "preprocesando": {
        "next_state": "preprocesado",
        "task_name": None,  # worker updates estado directly
        "queue": None,
    },
    "preprocesado": {
        "next_state": "clasificando",
        "task_name": "run_glaser_classifier",
        "queue": "heavy",
    },
    "clasificando": {
        "next_state": "clasificado",
        "task_name": None,  # classifier worker updates estado directly
        "queue": None,
    },
    "clasificado": {
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
    "extrayendo": {
        "next_state": "incidentes_extraidos",
        "task_name": None,  # heavy worker updates estado directly
        "queue": None,
    },
    "incidentes_extraidos": {
        "next_state": None,  # terminal (espera el lote para open coding)
        "task_name": None,
        "queue": None,
    },
    "procesando": {
        "next_state": "listo",  # legacy: open coding completado
        "task_name": None,
        "queue": None,
    },
    "listo": {
        "next_state": None,  # terminal (open coding completado)
        "task_name": None,
        "queue": None,
    },
    "procesado": {
        "next_state": None,  # terminal (alias legacy de incidentes_extraidos)
        "task_name": None,
        "queue": None,
    },
    "codificando": {
        "next_state": "codificado",
        "task_name": None,
        "queue": None,
    },
    "codificado": {
        "next_state": None,  # terminal
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

        # Fan out to every doc that still needs work, in sort_order. Workers
        # report back through the transition chain, which keeps a single
        # pipeline run consistent.
        dispatched_segment = 0
        dispatched_classify = 0
        dispatched_agents = 0
        skipped = 0
        task_ids = {"segment": [], "classify": [], "agents": []}

        # Estados terminales o de codificación: no se re-despachan. Los
        # transitorios tampoco: hay una tarea en vuelo y re-despacharla la
        # duplicaría (Stop los devuelve a 'crudo').
        skip_estados = {
            "incidentes_extraidos",
            "procesado",
            "listo",
            "codificando",
            "codificado",
            "resumido",
            "error",
            "preprocesando",
            "clasificando",
            "segmentando",
            "procesando",
            "extrayendo",
            "resumiendo",
        }

        if force:
            # Forzar desde cero: reset all docs and re-clasify every one of them.
            for row in docs:
                doc_id = str(row[0])
                metadatos = self._parse_metadatos(row[2])
                self._reset_document(doc_id)
                task = self._dispatch("crudo", doc_id, project_id, metadatos, run)
                if task:
                    dispatched_classify += 1
                    task_ids["classify"].append(
                        {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                    )
        else:
            for row in docs:
                doc_id = str(row[0])
                estado = (row[1] or "crudo").strip()
                metadatos = self._parse_metadatos(row[2])

                if estado in skip_estados:
                    skipped += 1
                    continue

                # Classify-first: la clasificación vive en metadatos
                # (`glaser_blocks`), no en los segmentos.
                has_classification = bool(
                    metadatos.get("glaser_blocks") or metadatos.get("texto_clasificado")
                )
                n_segs = self._count_segments(doc_id, self.db)
                n_classified = self._count_classified_segments(doc_id, self.db)
                n_codes = self._count_codes(doc_id, self.db)
                n_incidents = self._count_incidents(doc_id, self.db)

                if not has_classification:
                    # 1. Clasificar el texto. Sólo 'crudo' y 'preprocesado'
                    #    transicionan a 'clasificando'; un doc en un estado
                    #    posterior sin bloques es una inconsistencia (corrida
                    #    interrumpida o escalera anterior), así que se alinea su
                    #    estado sin borrar datos para que el lock optimista del
                    #    dispatch aplique.
                    if estado not in ("crudo", "preprocesado"):
                        self._force_estado(doc_id, "crudo")
                        estado = "crudo"
                    task = self._dispatch(estado, doc_id, project_id, metadatos, run)
                    if task:
                        dispatched_classify += 1
                        task_ids["classify"].append(
                            {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                        )
                elif n_segs == 0 or n_classified == 0:
                    # 2. Segmentar heredando la etiqueta del tramo de origen.
                    #    Re-segmentar reemplaza los segmentos viejos; los
                    #    bloques clasificados de metadatos no se tocan.
                    if estado != "clasificado":
                        self._force_estado(doc_id, "clasificado")
                    task = self._dispatch(
                        "clasificado", doc_id, project_id, metadatos, run
                    )
                    if task:
                        dispatched_segment += 1
                        task_ids["segment"].append(
                            {"doc_id": doc_id, "task_id": task["celery_task_id"]}
                        )
                elif n_incidents == 0 and n_codes == 0:
                    # 3. Extraer incidentes de los segmentos baseline_data.
                    if estado != "segmentado":
                        self._force_estado(doc_id, "segmentado")
                    task = self._dispatch(
                        "segmentado", doc_id, project_id, metadatos, run
                    )
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
            "need_classify": dispatched_classify,
            "need_agents": dispatched_agents,
            "already_done": skipped,
        }
        self.db.commit()

        # If all docs already reached batch-ready, trigger Phase B directly
        # (no per-document transition will fire it).
        ready = self.db.execute(
            text(
                "SELECT COUNT(*) FROM documentos WHERE proyecto_id = :pid "
                "AND TRIM(estado) IN ('listo', 'incidentes_extraidos', 'procesado')"
            ),
            {"pid": project_id},
        ).fetchone()[0]
        if ready == len(docs) and ready >= 3:
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

    @staticmethod
    def _parse_metadatos(raw_meta) -> dict:
        """Normaliza los metadatos de un documento (dict, JSON string o vacío)."""
        if isinstance(raw_meta, dict):
            return raw_meta
        if isinstance(raw_meta, str):
            try:
                return __import__("json").loads(raw_meta)
            except Exception:
                return {}
        return {}

    def _force_estado(self, doc_id: str, estado: str):
        """Alinea ``documentos.estado`` con el paso que toca despachar.

        Sólo se usa cuando la BD y el estado declarado no coinciden (corrida
        interrumpida o escalera anterior). No borra datos: deja el documento en
        el estado que espera el lock optimista de ``_dispatch``.
        """
        self.db.execute(
            text("UPDATE documentos SET estado = :est WHERE id = :did"),
            {"est": estado, "did": doc_id},
        )
        self.db.flush()

    def _reset_document(self, doc_id: str):
        """Resetea un documento a estado crudo (para force=True)."""
        # Hijas primero: sus FK a segmentos.id no tienen ON DELETE.
        # Los incidentes se anclan al documento: `extracted_incidents.segmento_id`
        # es legacy y queda NULL, así que no sirve para localizarlos.
        self.db.execute(
            text("DELETE FROM extracted_incidents WHERE documento_id = :did"),
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
            text("DELETE FROM segmentos WHERE documento_id = :did"),
            {"did": doc_id},
        )
        self.db.execute(
            text("DELETE FROM document_stage_progress WHERE documento_id = :did"),
            {"did": doc_id},
        )
        self.db.execute(
            text(
                "UPDATE documentos SET estado = 'crudo', "
                "metadatos = metadatos - 'texto_preprocesado' - 'preprocess_warning' - 'texto_puntuado' "
                "- 'texto_clasificado' - 'baseline_tags' - 'glaser_blocks' - 'glaser_used_fallback' "
                "WHERE id = :did"
            ),
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
        """Despacha la siguiente tarea y crea PipelineTask.

        El paso sale de ``_resolve_next`` (fuente de verdad, incluye la
        degradación a clasificación cuando no hay workers nlp); ``TRANSITIONS``
        queda como respaldo para los estados legacy que el resolver no conoce.
        """
        trans = TRANSITIONS.get(from_state)
        # El resolver de agents/transitions es la fuente de verdad (degradación
        # cuando no hay workers nlp). Import local: importarlo a nivel módulo
        # crea un ciclo con este servicio.
        try:
            from app.agents.transitions import _resolve_next
        except Exception:  # pragma: no cover - best effort
            _resolve_next = None
        if _resolve_next is not None:
            resolved = _resolve_next(from_state)
            if resolved:
                next_state, task_name, queue = resolved
                trans = {
                    "next_state": next_state,
                    "task_name": task_name,
                    "queue": queue,
                }
        if not trans or not trans["task_name"]:
            return None

        # Update document estado (optimistic locking)
        result = self.db.execute(
            text(
                "UPDATE documentos SET estado = :next "
                "WHERE id = :did AND estado = :from_st"
            ),
            {"next": trans["next_state"], "did": doc_id, "from_st": from_state},
        )
        self.db.flush()

        # Optimistic lock: si el doc ya no estaba en from_state, otro proceso
        # lo movió. No despachar trabajo stale.
        if result.rowcount == 0:
            logger.info(
                "Doc %s not in expected state '%s'; skipping dispatch",
                doc_id,
                from_state,
            )
            return None

        # Dispatch Celery task via shared app instance
        if trans["task_name"] == "segmentar_documento":
            # La segmentación parte siempre del texto plano: la clasificación ya
            # está en metadatos y los segmentos heredan la etiqueta de su tramo.
            texto = (
                metadatos.get("texto_preprocesado")
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
    def _count_classified_segments(doc_id: str, session=None) -> int:
        """Cuenta segmentos que ya tienen categoría Glaser."""
        sql = (
            "SELECT COUNT(*) FROM segmentos "
            "WHERE documento_id = :did AND tipo_dato_glaser IS NOT NULL"
        )
        if session is not None:
            return session.execute(text(sql), {"did": doc_id}).fetchone()[0]
        import os as _os

        from sqlalchemy import create_engine

        url = _os.getenv("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        engine = create_engine(url)
        from sqlalchemy.orm import Session as SyncSession

        with SyncSession(engine) as s:
            return s.execute(text(sql), {"did": doc_id}).fetchone()[0]

    @staticmethod
    def _count_incidents(doc_id: str, session=None) -> int:
        """Cuenta incidentes extraídos del documento (paso 3 de la cadena)."""
        # Se consulta por documento_id: extracted_incidents.segmento_id es legacy.
        sql = (
            "SELECT COUNT(ei.id) FROM extracted_incidents ei "
            "WHERE ei.documento_id = :did"
        )
        if session is not None:
            return session.execute(text(sql), {"did": doc_id}).fetchone()[0]
        import os as _os

        from sqlalchemy import create_engine

        url = _os.getenv("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        engine = create_engine(url)
        from sqlalchemy.orm import Session as SyncSession

        with SyncSession(engine) as s:
            return s.execute(text(sql), {"did": doc_id}).fetchone()[0]

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
