"""Pipeline execution endpoints — dispara stages y devuelve task_ids para polling."""

import asyncio
import logging
from uuid import UUID, uuid4

from app.core.celery_app import celery_app
from app.core.context_config import context_config
from app.db.database import get_db
from app.models.domain.document import Documento
from app.models.domain.project import Proyecto
from app.models.domain.user import Usuario
from app.schemas.hitl import PauseConfigRequest
from app.services.auth import get_current_user
from app.services.pipeline_state import (
    close_finished_runs,
    close_idle_runs,
    pipeline_really_running,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["pipeline"])

logger = logging.getLogger(__name__)


@router.post("/projects/{project_id}/pipeline/run-stage/{stage_name}")
async def run_pipeline_stage(
    project_id: UUID,
    stage_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Dispara una etapa del pipeline y devuelve los task_ids para polling.

    Stages: upload, precoding, open_coding, cross_doc, pattern_of_interest,
            selective, saturation
    """
    result = {"stage": stage_name, "project_id": str(project_id), "task_ids": []}

    # ── Obtener documentos del proyecto ──────────────────────────────
    docs_result = await db.execute(
        select(Documento).where(Documento.proyecto_id == project_id)
    )
    docs = docs_result.scalars().all()

    if stage_name == "upload":
        if not docs:
            raise HTTPException(400, "No documents uploaded. Upload documents first.")
        # Upload stage: verificar que todos tengan segmentos o disparar segmentación
        for doc in docs:
            task = celery_app.send_task(
                "segmentar_documento",
                args=[
                    (doc.metadatos or {}).get("texto_preprocesado")
                    or (doc.metadatos or {}).get("texto_extraido", ""),
                    1024,
                    doc.original_filename,
                    "TEXTO",
                    "",
                    str(doc.id),
                ],
                queue="nlp",
            )
            result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "precoding":
        # Precoding happens inside process_document_agents_a
        # Just return status based on document states
        result["status"] = "checking"
        result["note"] = "Precoding runs as part of open_coding phase"

    elif stage_name == "open_coding":
        # Classify-first: `process_document_agents_a` consume los segmentos ya
        # etiquetados, así que sólo entran los 'segmentado'. Un doc en
        # 'clasificado' todavía necesita segmentarse (paso anterior de la
        # escalera) y los terminales ya no se re-despachan.
        for doc in docs:
            if (doc.estado or "").strip() == "segmentado":
                task = celery_app.send_task(
                    "process_document_agents_a",
                    args=[str(doc.id), str(project_id)],
                    queue="heavy",
                )
                result["task_ids"].append(task.id)
        if not result["task_ids"]:
            result["status"] = "already_processed"
        else:
            result["status"] = "dispatched"

    elif stage_name == "cross_doc":
        # REGLA: la codificación selectiva no puede arrancar sin patrón de
        # interés elegido. Antes de este guard el coordinator corría con
        # `chosen_concern` nulo y la etapa entera quedaba sin objeto de estudio.
        concern_row = await db.execute(
            text("SELECT chosen_concern FROM proyectos WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        concern = concern_row.fetchone()
        if not (concern and (concern[0] or "").strip()):
            raise HTTPException(
                409,
                "Elegí el patrón de interés en el HITL de codificación abierta "
                "antes de iniciar la codificación.",
            )

        # Limpiar los marcadores Phase-B obsoletos para que un run manual
        # siempre despache (process_synthesis_agents_b se salta si ya están).
        await db.execute(
            text(
                "DELETE FROM processing_states "
                "WHERE entity_type = 'project' AND entity_id = :pid "
                "AND step LIKE 'phase_b_run_%'"
            ),
            {"pid": str(project_id)},
        )
        await db.commit()
        task = celery_app.send_task(
            "process_synthesis_agents_b",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

        # Tracking: sin esta fila /pipeline/log no ve la fase en vuelo (la etapa
        # se queda sin spinner) y /admin/projects/{id}/stop no puede revocarla.
        await _track_pipeline_task(
            db,
            project_id,
            None,
            task.id,
            "process_synthesis_agents_b",
            "heavy",
            None,
        )

    elif stage_name == "pattern_of_interest":
        # Redirigido al selective_coding_coordinator (Fase A)
        task = celery_app.send_task(
            "selective_coding_coordinator",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "selective":
        # Redirigido al selective_coding_coordinator (pipeline completo)
        task = celery_app.send_task(
            "selective_coding_coordinator",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "saturation":
        # Saturation runs via analysis endpoint — no Celery task to dispatch
        result["status"] = "ready"
        result["note"] = "Use GET /projects/{pid}/analysis/saturation-gaps"

    # ── Nuevos stages (selective coding coordinator) ──
    elif stage_name == "find_cc":
        task = celery_app.send_task(
            "selective_coding_coordinator",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "reduce":
        task = celery_app.send_task(
            "selective_coding_coordinator",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "saturate":
        task = celery_app.send_task(
            "selective_coding_coordinator",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "build_db":
        task = celery_app.send_task(
            "selective_coding_coordinator",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "playground":
        task = celery_app.send_task(
            "invoke_graph",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    else:
        raise HTTPException(400, f"Unknown stage: {stage_name}")

    return result


@router.get("/projects/{project_id}/pipeline/log")
async def get_pipeline_log(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Log detallado por documento: qué pasos se completaron y qué falta.
    Mira la DB real (segmentos, códigos) — no solo el campo estado.
    """
    from sqlalchemy import text

    docs_result = await db.execute(
        select(Documento).where(Documento.proyecto_id == project_id)
    )
    docs = docs_result.scalars().all()

    if not docs:
        return {
            "project_id": str(project_id),
            "documents": [],
            "summary": {
                "total": 0,
                "need_segment": 0,
                "need_classify": 0,
                "need_agents": 0,
                "done": 0,
                "failed": 0,
                "categories": 0,
                "docs_inconsistent": 0,
                "docs_need_classify": 0,
                "playground_ready": False,
                "open_coding_batch_size": _open_coding_batch_size(),
            },
        }

    doc_ids = [d.id for d in docs]

    # Contar segmentos por documento
    seg_counts = {}
    seg_result = await db.execute(
        text(
            "SELECT documento_id, COUNT(*) FROM segmentos "
            "WHERE documento_id = ANY(:ids) GROUP BY documento_id"
        ),
        {"ids": doc_ids},
    )
    for row in seg_result:
        seg_counts[str(row[0])] = row[1]

    # Contar códigos asignados por documento (via segmentos)
    code_counts = {}
    code_result = await db.execute(
        text(
            "SELECT s.documento_id, COUNT(cs.segmento_id) "
            "FROM segmentos s "
            "LEFT JOIN codigos_segmento cs ON cs.segmento_id = s.id "
            "WHERE s.documento_id = ANY(:ids) GROUP BY s.documento_id"
        ),
        {"ids": doc_ids},
    )
    for row in code_result:
        code_counts[str(row[0])] = row[1]

    # Contar segmentos ya clasificados (tipo_dato_glaser) por documento
    clasif_counts = {}
    clasif_result = await db.execute(
        text(
            "SELECT documento_id, COUNT(*) FROM segmentos "
            "WHERE documento_id = ANY(:ids) AND tipo_dato_glaser IS NOT NULL "
            "GROUP BY documento_id"
        ),
        {"ids": doc_ids},
    )
    for row in clasif_result:
        clasif_counts[str(row[0])] = row[1]

    # Clasificación real por documento. Se consulta la DB en vez de inferirla
    # del estado: bajo la escalera classify-first 'clasificado' es un estado
    # transitorio y los metadatos son la única prueba de que el texto quedó
    # etiquetado (los docs legacy usan texto_clasificado).
    class_flags = {}
    class_result = await db.execute(
        text(
            "SELECT id, (metadatos ? 'glaser_blocks') AS has_blocks, "
            "(metadatos ? 'texto_clasificado') AS has_legacy "
            "FROM documentos WHERE id = ANY(:ids)"
        ),
        {"ids": doc_ids},
    )
    for row in class_result:
        class_flags[str(row[0])] = bool(row[1]) or bool(row[2])

    # Contar incidentes extraídos por documento
    inc_counts = {}
    inc_result = await db.execute(
        text(
            "SELECT documento_id, COUNT(*) FROM extracted_incidents "
            "WHERE documento_id = ANY(:ids) GROUP BY documento_id"
        ),
        {"ids": doc_ids},
    )
    for row in inc_result:
        inc_counts[str(row[0])] = row[1]

    # Contar categorías del proyecto
    cat_result = await db.execute(
        text("SELECT COUNT(*) FROM categorias WHERE proyecto_id = :pid"),
        {"pid": project_id},
    )
    cat_count = cat_result.scalar() or 0

    # Construir log por documento
    doc_logs = []
    for doc in docs:
        did = str(doc.id)
        n_segs = seg_counts.get(did, 0)
        n_codes = code_counts.get(did, 0)
        n_clasif = clasif_counts.get(did, 0)
        n_incidents = inc_counts.get(did, 0)
        has_classification = class_flags.get(did, False)
        has_text = bool(
            (doc.metadatos or {}).get("texto_extraido")
            or (doc.metadatos or {}).get("texto_preprocesado")
            or (doc.metadatos or {}).get("texto_original")
        )

        # Determinar qué pasos se completaron
        steps_done = {
            "text_extracted": has_text,
            "punctuation_fixed": bool(
                (doc.metadatos or {}).get("texto_puntuado", False)
            ),
            "segmented": n_segs > 0,
            "coded": n_codes > 0,
            "agents_done": doc.estado in ("listo", "sintetizado") and n_codes > 0,
            "synthesis_done": doc.estado == "sintetizado",
            "classified": has_classification,
            "incidents": n_incidents > 0,
        }

        # Determinar qué falta. Escalera classify-first: el clasificador corre
        # sobre el texto y los segmentos se derivan después, así que la
        # clasificación se comprueba ANTES de los segmentos (un doc clasificado
        # sin segmentos está a un paso de segmentar, no de clasificar).
        if doc.estado == "error":
            next_action = "error"
        elif not has_text:
            next_action = "extract_text"
        elif not has_classification:
            next_action = "classify"
        elif not n_segs:
            next_action = "segment"
        elif doc.estado in ("incidentes_extraidos", "codificando"):
            # Pipeline por incidentes: los agentes A ya corrieron y NO escriben
            # en codigos_segmento (los códigos viven en incident_groups /
            # categorias). Sin esta rama un doc en 'incidentes_extraidos' cuenta
            # como "run_agents" para siempre: la etapa open_coding nunca llega a
            # "done" y el resumen pide reejecutar agentes que no aplican.
            next_action = "run_synthesis"
        elif doc.estado in ("procesado", "codificado", "sintetizado"):
            # Estados terminales (ver skip_estados del orquestador).
            next_action = "done"
        elif not n_codes:
            next_action = "run_agents"
        elif doc.estado == "listo":
            next_action = "run_synthesis"
        else:
            next_action = "run_agents"

        # Códigos que describen un estado imposible bajo classify-first. El
        # frontend los usa para avisar en vez de ofrecer un paso que el backend
        # va a rechazar (un doc 'segmentado' sin segmentos, por ejemplo).
        inconsistencies = []
        if n_segs > 0 and not has_classification:
            inconsistencies.append("missing_classified")
        if (
            doc.estado in ("incidentes_extraidos", "procesado", "codificado", "listo")
            and n_segs == 0
        ):
            inconsistencies.append("missing_segmented")
        if doc.estado == "segmentado" and n_segs == 0:
            inconsistencies.append("segmented_without_segments")
        if n_segs > 0 and n_clasif < n_segs:
            inconsistencies.append("segments_unclassified")

        doc_logs.append(
            {
                "document_id": did,
                "filename": doc.original_filename,
                "estado": doc.estado,
                "steps": steps_done,
                "segments_count": n_segs,
                "codes_count": n_codes,
                "has_classification": has_classification,
                "classified_count": n_clasif,
                "incidents_count": n_incidents,
                "inconsistencies": inconsistencies,
                "next_action": next_action,
            }
        )

    # Resumen con nuevos estados
    # docs that haven't been segmented yet — count ALL non-segmented docs
    docs_need_segment = sum(
        1
        for d in doc_logs
        if d["next_action"] in ("segment", "extract_text")
        or (d["next_action"] not in ("done", "error") and d["segments_count"] == 0)
    )
    docs_need_agents = sum(1 for d in doc_logs if d["next_action"] == "run_agents")
    docs_need_classify = sum(1 for d in doc_logs if d["next_action"] == "classify")
    docs_need_synthesis = sum(
        1 for d in doc_logs if d["next_action"] == "run_synthesis"
    )
    docs_done = sum(1 for d in doc_logs if d["next_action"] == "done")
    docs_inconsistent = sum(1 for d in doc_logs if d["inconsistencies"])
    docs_sintetizados = sum(1 for d in docs if d.estado == "sintetizado")
    docs_failed = sum(1 for d in doc_logs if d["next_action"] == "error")
    error_list = [
        {
            "document_id": d["document_id"],
            "filename": d["filename"],
            "estado": d["estado"],
        }
        for d in doc_logs
        if d["next_action"] == "error"
    ]

    # Count failed system tasks (Phase B, etc.) from active pipeline run
    failed_tasks = 0
    try:
        run_row = await db.execute(
            text(
                "SELECT COUNT(*) FROM pipeline_tasks "
                "JOIN pipeline_runs ON pipeline_tasks.run_id = pipeline_runs.id "
                "WHERE pipeline_runs.project_id = :pid "
                "AND pipeline_runs.status = 'running' "
                "AND pipeline_tasks.status IN ('failed', 'cancelled')"
            ),
            {"pid": project_id},
        )
        failed_tasks = run_row.scalar() or 0
    except Exception:
        pass

    # Runs marcados 'running'. Se reconcilian con Celery antes de contarlos para
    # que un run cuyo trabajo ya terminó no deje el botón "cerrar ejecución
    # anterior" colgado en la UI: nadie cierra el último run de una sesión (solo
    # el siguiente despacho, los memos o el botón manual lo hacían). Si no se
    # pudo leer el estado real, se cae al conteo crudo sin cerrar nada.
    open_runs = 0
    try:
        reconciled = await close_finished_runs(db, project_id)
        if reconciled is None:
            open_runs = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM pipeline_runs "
                        "WHERE project_id = :pid AND status = 'running'"
                    ),
                    {"pid": str(project_id)},
                )
            ).scalar() or 0
        else:
            open_runs = reconciled[1]
    except Exception:
        logger.debug("No se pudieron reconciliar pipeline_runs", exc_info=True)

    # ── Agentes con trabajo en vuelo ──
    # pipeline_tasks solo registra 'queued': nada la pasa a 'running' ni a
    # 'completed' (solo on_failure escribe 'failed'), así que el estado real se
    # consulta al result backend de Celery. La ventana de 4 h descarta filas
    # huérfanas de runs abandonados, cuyos task ids Celery ya olvidó y que
    # responderían 'PENDING' para siempre.
    running_agents: list[str] = []
    # Agentes cuya tarea terminó con SUCCESS dentro de la ventana. Sin esto,
    # recargar la página a mitad de ejecución deja al agente fuera de
    # completedAgents (estado de cliente) y vuelve a mostrar ▶ en vez de ↻.
    succeeded_agents: list[str] = []
    # Etapas cuyo orquestador de fase está en vuelo ("data_management",
    # "open_coding"). Las tareas de fase no corresponden a ningún agente de la
    # UI, así que sin esto lanzar la codificación no pinta ningún spinner.
    running_phases: list[str] = []
    try:
        pending_rows = (
            await db.execute(
                text(
                    "SELECT pt.task_name, pt.celery_task_id "
                    "FROM pipeline_tasks pt "
                    "JOIN pipeline_runs pr ON pr.id = pt.run_id "
                    "WHERE pr.project_id = :pid "
                    "AND pt.status = 'queued' "
                    "AND pt.creado_en > now() - interval '4 hours' "
                    "ORDER BY pt.creado_en DESC "
                    "LIMIT 50"
                ),
                {"pid": str(project_id)},
            )
        ).all()
        if pending_rows:
            tids = [r[1] for r in pending_rows if r[1]]
            states = await asyncio.to_thread(_celery_task_states, tids)
            for task_name, tid in pending_rows:
                state = states.get(tid)
                in_flight = state in (
                    "PENDING",
                    "STARTED",
                    "RETRY",
                    "RECEIVED",
                )
                agent_id = _TASK_TO_AGENT_ID.get(task_name or "")
                if agent_id:
                    if in_flight:
                        if agent_id not in running_agents:
                            running_agents.append(agent_id)
                    elif state == "SUCCESS":
                        if agent_id not in succeeded_agents:
                            succeeded_agents.append(agent_id)
                    continue
                # Orquestador de fase: se refleja a nivel de etapa.
                stage_key = _PHASE_TASK_TO_STAGE.get(task_name or "")
                if in_flight and stage_key and stage_key not in running_phases:
                    running_phases.append(stage_key)
    except Exception:
        logger.debug("No se pudo resolver running_agents", exc_info=True)

    # Un mismo agente puede tener un lanzamiento viejo en vuelo y otro nuevo ya
    # terminado; "en vuelo" gana, que es lo que el usuario ve en pantalla.
    succeeded_agents = [a for a in succeeded_agents if a not in running_agents]

    return {
        "project_id": str(project_id),
        "documents": doc_logs,
        "summary": {
            "total": len(docs),
            "need_segment": docs_need_segment,
            "need_classify": docs_need_classify,
            "need_agents": docs_need_agents,
            "docs_inconsistent": docs_inconsistent,
            "docs_need_classify": docs_need_classify,
            "need_synthesis": docs_need_synthesis,
            "sintetizados": docs_sintetizados,
            "done": docs_done,
            "failed": docs_failed,
            "failed_tasks": failed_tasks,
            "errors": error_list,
            "categories": cat_count,
            "project_state": await _get_project_state(db, project_id),
            "playground_ready": docs_sintetizados == len(docs) and cat_count > 0,
            "open_coding_batch_size": _open_coding_batch_size(),
            "running_agents": running_agents,
            "succeeded_agents": succeeded_agents,
            "running_phases": running_phases,
            "open_runs": open_runs,
        },
    }


@router.get("/projects/{project_id}/pipeline/decisions")
async def get_pipeline_decisions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Devuelve todas las decisiones HITL aceptadas con sus propuestas completas.
    Consumido por el PlaygroundDataPanel para mostrar el contexto del pipeline.
    """
    from sqlalchemy import text

    rows = await db.execute(
        text(
            "SELECT gate_name, proposal, critic_verdict, status, "
            "researcher_decision, researcher_note, decided_at "
            "FROM hitl_decisions "
            "WHERE project_id = :pid AND status = 'accepted' "
            "ORDER BY creado_en ASC"
        ),
        {"pid": project_id},
    )

    decisions = []
    for row in rows:
        decisions.append(
            {
                "gate": row[0],
                "proposal": row[1] if isinstance(row[1], dict) else {},
                "critic_verdict": row[2] if isinstance(row[2], dict) else {},
                "status": row[3],
                "decision": row[4],
                "note": row[5],
                "decided_at": str(row[6]) if row[6] else None,
            }
        )

    # También devolver conteo de saturación
    sat_rows = await db.execute(
        text(
            "SELECT c.nombre, "
            "COUNT(ps.id) FILTER (WHERE ps.did_state_expand = false) AS no_expand "
            "FROM categorias c "
            "LEFT JOIN paradigm_states ps ON c.id = ps.code_id "
            "WHERE c.proyecto_id = :pid AND COALESCE(c.puntaje_relevancia, 0) >= 4 "
            "GROUP BY c.id, c.nombre"
        ),
        {"pid": project_id},
    )

    saturation = {}
    for row in sat_rows:
        saturation[row[0]] = {
            "no_expansion_count": row[1] or 0,
            "saturated": (row[1] or 0) >= 3,
        }

    return {
        "project_id": str(project_id),
        "decisions": decisions,
        "saturation": saturation,
    }


@router.get("/projects/{project_id}/pipeline/status")
async def get_pipeline_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Devuelve el estado actual del pipeline para un proyecto.
    Revisa documentos, segmentos, códigos, e hipótesis.
    """
    docs_result = await db.execute(
        select(Documento).where(Documento.proyecto_id == project_id)
    )
    docs = docs_result.scalars().all()

    from sqlalchemy import text

    # Count segments
    seg_count = 0
    if docs:
        doc_ids = [d.id for d in docs]
        seg_result = await db.execute(
            text("SELECT COUNT(*) FROM segmentos WHERE documento_id = ANY(:ids)"),
            {"ids": doc_ids},
        )
        seg_count = seg_result.scalar() or 0

    # Count categories
    cat_result = await db.execute(
        text("SELECT COUNT(*) FROM categorias WHERE proyecto_id = :pid"),
        {"pid": project_id},
    )
    cat_count = cat_result.scalar() or 0

    # Count hypotheses
    hyp_result = await db.execute(
        text("SELECT COUNT(*) FROM hypotheses WHERE project_id = :pid"),
        {"pid": project_id},
    )
    hyp_count = hyp_result.scalar() or 0

    # Determine pipeline progress
    stages_status = {
        "upload": "done" if docs else "pending",
        "precoding": "done"
        if any(d.estado not in ("crudo",) for d in docs)
        else "pending",
        "open_coding": "done"
        if cat_count > 0
        else ("in_progress" if seg_count > 0 else "pending"),
        "cross_doc": "done"
        if hyp_count > 0
        else ("in_progress" if cat_count > 0 else "pending"),
        "pattern_of_interest": "pending",
        "selective": "pending",
        "saturation": "pending",
    }

    return {
        "project_id": str(project_id),
        "documents": len(docs),
        "segments": seg_count,
        "categories": cat_count,
        "hypotheses": hyp_count,
        "stages": stages_status,
    }


@router.post("/projects/{project_id}/pipeline/close-idle-runs")
async def close_idle_pipeline_runs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Cierra los runs que quedaron en 'running' sin trabajo en vuelo.

    ``pipeline_runs.status`` no tiene dueño: los runs se crean 'running' y solo
    ``POST /admin/projects/{id}/stop`` los cierra. Si el worker muere a mitad, el
    proyecto queda marcado como "pipeline en ejecución" para siempre. Este
    endpoint reconcilia con Celery como fuente de verdad y no revoca tareas ni
    toca documentos (a diferencia de /stop).
    """
    return {"closed": await close_idle_runs(db, project_id)}


@router.post("/projects/{project_id}/pipeline/run")
async def run_pipeline_orchestrated(
    project_id: UUID,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Orchestrator único del pipeline.
    Recibe `{"force": bool}` y delega en el pipeline el cálculo de qué toca
    despachar (classify → segmentar → extraer).

    Returns:
        Resumen del pipeline con los task_ids encolados.
    """

    force = (body or {}).get("force", False)

    # ── 1. Obtener docs del proyecto ──
    docs_result = await db.execute(
        select(Documento).where(Documento.proyecto_id == project_id)
    )
    docs = docs_result.scalars().all()

    if not docs:
        return {"status": "no_docs", "message": "No hay documentos en el proyecto"}

    # Clean old pipeline logs
    try:
        import os as _os

        import redis.asyncio as _aredis

        _r = _aredis.from_url(_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        await _r.delete(f"pipeline_logs:{project_id}")
        await _r.close()
    except Exception:
        pass

    # Qué falta por documento lo decide el orchestrator (mira la clasificación de
    # metadatos, los segmentos, los incidentes y los códigos), así que aquí sólo
    # se delega: duplicar esa decisión en el API fue lo que dejó la escalera
    # segment-first clavada en este archivo.

    # ── Delegar al Orchestrator centralizado ──
    import os as _os

    from app.services.pipeline_orchestrator import PipelineOrchestrator
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SyncSession

    sync_url = _os.getenv("DATABASE_URL", "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    sync_engine = create_engine(sync_url)
    with SyncSession(sync_engine) as sync_db:
        orch = PipelineOrchestrator(sync_db)
        result = orch.start_pipeline(project_id, force)

    return result


@router.get("/projects/{project_id}/pipeline/tail")
async def tail_pipeline_logs(
    project_id: UUID,
    since: float = 0,
):
    """Devuelve logs del pipeline en tiempo real desde Redis."""
    import json as _json
    import os as _os

    import redis.asyncio as _aredis

    redis_url = _os.getenv("REDIS_URL", "redis://redis:6379/0").replace(
        "redis://", "redis://default@"
    )
    try:
        r = _aredis.from_url(redis_url)
        key = f"pipeline_logs:{project_id}"
        entries = await r.lrange(key, 0, -1)
        await r.close()

        logs = []
        for e in entries:
            try:
                entry = _json.loads(e)
                if entry.get("ts", 0) > since:
                    logs.append(entry)
            except Exception:
                pass
        return {"logs": logs[-100:], "count": len(logs)}
    except Exception:
        return {"logs": [], "count": 0, "error": "redis_unavailable"}


@router.get("/projects/{project_id}/agent-logs")
async def get_agent_logs(project_id: UUID):
    """Returns all agent prompt/response logs for a project."""
    import json as _json
    import os as _os

    import redis.asyncio as _aredis

    redis_url = _os.getenv("REDIS_URL", "redis://redis:6379/0").replace(
        "redis://", "redis://default@"
    )
    try:
        r = _aredis.from_url(redis_url)
        items = await r.lrange(f"agent_logs:{project_id}", 0, -1)
        await r.close()
        return [_json.loads(item) for item in items]
    except Exception:
        return []


@router.get("/projects/{project_id}/agent-memos")
async def get_agent_memos(
    project_id: UUID,
    include_intermediate: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Returns agent outputs as memo cards. Uses agent_families for grouping."""
    from sqlalchemy import text

    # ── Families metadata ──
    fam_rows = await db.execute(
        text(
            "SELECT family, label, icon, description FROM agent_families ORDER BY family"
        )
    )
    families = [
        {"key": r[0], "label": r[1], "icon": r[2], "description": r[3]}
        for r in fam_rows
    ]

    memos = []
    is_final_filter = (
        "TRUE" if not include_intermediate else "TRUE"
    )  # always include finals

    # ── A1: Population Contexts (descriptive_data, PRO) ──
    pc_rows = await db.execute(
        text(
            "SELECT pc.id, pc.version, pc.surprising_details, pc.language_patterns, "
            "pc.data_production_context, pc.creado_en "
            "FROM population_contexts pc "
            "WHERE pc.proyecto_id = :pid "
            "ORDER BY pc.version DESC LIMIT 20"
        ),
        {"pid": project_id},
    )
    for row in pc_rows:
        memos.append(
            {
                "id": f"pc-{row[0]}",
                "family": "descriptive_data",
                "agentId": "A1 (PRO)",
                "isFinal": True,
                "documentName": f"Population Context v{row[1]}",
                "timestamp": str(row[5]) if row[5] else "",
                "data": {
                    "surprising_details": row[2] or "",
                    "language_patterns": row[3] or "",
                    "data_production_context": row[4] or "",
                    "version": row[1],
                },
            }
        )

    # ── A2: Document Processes (descriptive_data, PRO) ──
    dp_rows = await db.execute(
        text(
            "SELECT dp.id, dp.process_description, dp.similarity_to_previous, "
            "dp.difference_from_previous, dp.prime_mover, dp.prime_mover_confidence, "
            "dp.creado_en, d.original_filename "
            "FROM document_processes dp "
            "JOIN documentos d ON dp.documento_id = d.id "
            "WHERE dp.proyecto_id = :pid "
            "ORDER BY dp.creado_en DESC LIMIT 30"
        ),
        {"pid": project_id},
    )
    for row in dp_rows:
        data = {
            "process_description": row[1] or "",
            "similarity_to_previous": row[2] or "",
            "difference_from_previous": row[3] or "",
        }
        if row[4]:
            data["prime_mover"] = row[4]
            data["prime_mover_confidence"] = row[5] or "LOW"
        memos.append(
            {
                "id": f"dp-{row[0]}",
                "family": "descriptive_data",
                "agentId": "A2 (PRO)",
                "isFinal": True,
                "documentName": row[7] or "unknown",
                "timestamp": str(row[6]) if row[6] else "",
                "data": data,
            }
        )

    # ── B2: Categories (inductive_data, PRO) ──
    cat_rows = await db.execute(
        text(
            "SELECT c.id, c.nombre, c.definicion, c.puntaje_relevancia, c.es_central, c.creado_en "
            "FROM categorias c WHERE c.proyecto_id = :pid ORDER BY c.puntaje_relevancia DESC NULLS LAST LIMIT 30"
        ),
        {"pid": project_id},
    )
    for row in cat_rows:
        memos.append(
            {
                "id": f"cat-{row[0]}",
                "family": "inductive_data",
                "agentId": "B2 (PRO)",
                "isFinal": True,
                "documentName": f"{row[1]}{' ⭐' if row[4] else ''}",
                "timestamp": str(row[5]) if row[5] else "",
                "data": {
                    "nombre": row[1],
                    "definicion": row[2] or "",
                    "puntaje_relevancia": row[3],
                    "es_central": row[4] or False,
                },
            }
        )

    return {"memos": memos, "total": len(memos), "families": families}


# ── Mutation endpoints for memo editing ──

TABLE_MAP = {
    "pc": (
        "population_contexts",
        ["surprising_details", "language_patterns", "data_production_context"],
    ),
    "dp": (
        "document_processes",
        [
            "process_description",
            "similarity_to_previous",
            "difference_from_previous",
            "prime_mover",
        ],
    ),
    "cat": ("categorias", ["nombre", "definicion"]),
}

# Families served by GET .../agent-memos, expressed as TABLE_MAP prefixes so the
# bulk delete below cannot drift from the read side.
MEMO_FAMILY_PREFIXES = {
    "descriptive_data": ("pc", "dp"),
    "inductive_data": ("cat",),
}


def _resolve_memo_prefixes(family: str | None) -> tuple[str, ...]:
    """Map a ``family`` filter to TABLE_MAP prefixes. No filter = every family."""
    if not family or family.strip().lower() in ("all", "*"):
        return tuple(TABLE_MAP)
    key = family.strip().lower()
    if key in MEMO_FAMILY_PREFIXES:
        return MEMO_FAMILY_PREFIXES[key]
    if key in TABLE_MAP:
        return (key,)
    for prefix, (table, _) in TABLE_MAP.items():
        if key == table:
            return (prefix,)
    raise HTTPException(
        400,
        f"Familia desconocida: {family!r}. Valores válidos: "
        + ", ".join(sorted(MEMO_FAMILY_PREFIXES)),
    )


@router.delete("/projects/{project_id}/agent-memos")
async def delete_agent_memos(
    project_id: UUID,
    family: str | None = Query(
        None,
        description="Familia a eliminar (descriptive_data, inductive_data). "
        "Sin valor se eliminan todas.",
    ),
    tipo: str | None = Query(None, description="Alias de `family`."),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina los memos de agente que devuelve GET .../agent-memos.

    Borra de las mismas tablas que lee el GET (``TABLE_MAP``) en una sola
    transacción: si alguna fila tiene datos derivados (códigos, hipótesis,
    métricas…) la FK lo impide y no se borra nada.
    """
    from sqlalchemy.exc import IntegrityError

    proyecto = await db.get(Proyecto, project_id)
    if proyecto is None:
        raise HTTPException(404, "Proyecto no encontrado")
    if str(proyecto.creador_id) != str(current_user.id):
        raise HTTPException(403, "No autorizado")

    # Mismo gate que DELETE /projects/{id}/memos (memos.py): borrar entidades
    # con el pipeline en marcha deja a los agentes escribiendo en el vacío.
    # El estado se pide a Celery: los runs no se cierran nunca y su 'running'
    # dejaría el borrado bloqueado para siempre. `heal=True` aprovecha para
    # cerrar los que ya no tienen trabajo en vuelo.
    if await pipeline_really_running(db, project_id, heal=True):
        raise HTTPException(409, "Pausa el pipeline antes de eliminar entidades.")

    requested = family or tipo
    prefixes = _resolve_memo_prefixes(requested)

    by_table: dict[str, int] = {}
    try:
        for prefix in prefixes:
            table, _ = TABLE_MAP[prefix]
            result = await db.execute(
                text(f"DELETE FROM {table} WHERE proyecto_id = :pid"),
                {"pid": project_id},
            )
            by_table[table] = result.rowcount or 0
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Bulk agent-memo delete blocked by a foreign key in project %s: %s",
            project_id,
            exc,
        )
        raise HTTPException(
            409,
            "No se pueden eliminar estos memos: tienen datos derivados "
            "(códigos, hipótesis, métricas de saturación…). Elimina esos datos "
            "primero y vuelve a intentarlo.",
        ) from exc

    deleted = sum(by_table.values())
    if deleted == 0:
        await db.rollback()
        raise HTTPException(
            404,
            "No hay memos de agente que eliminar"
            + (f" en la familia '{requested}'" if requested else ""),
        )

    await db.commit()
    logger.info(
        "Deleted %d agent memos from project %s: %s", deleted, project_id, by_table
    )
    return {"deleted": deleted, "by_table": by_table, "family": requested or "all"}


@router.delete("/agent-outputs/{memo_id}")
async def delete_agent_output(
    memo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Delete an agent output. memo_id format: {prefix}-{uuid} (e.g. pc-xxx, dp-xxx, cat-xxx)

    Para categorías (cat-*) con source_memo_id, marca el memo de origen como
    absorbido en vez de dejarlo huérfano (sincronización Memo↔Entidad P4).
    """
    from sqlalchemy import text

    parts = memo_id.split("-", 1)
    if len(parts) != 2 or parts[0] not in TABLE_MAP:
        raise HTTPException(400, f"Invalid memo_id format: {memo_id}")
    prefix, row_id = parts
    table, _ = TABLE_MAP[prefix]

    # ── Sync: si es una categoría con source_memo_id, actualizar el memo ──
    # Se lee antes del DELETE (es la misma fila) pero el memo sólo se marca
    # cuando el borrado ha ocurrido de verdad.
    source_memo_id = None
    if prefix == "cat":
        source = await db.execute(
            text("SELECT source_memo_id FROM categorias WHERE id = :id"),
            {"id": row_id},
        )
        source_row = source.fetchone()
        if source_row and source_row[0]:
            source_memo_id = str(source_row[0])

    result = await db.execute(
        text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id}
    )
    if result.rowcount == 0:
        await db.rollback()
        raise HTTPException(404, f"Agent output no encontrado: {memo_id}")

    if source_memo_id:
        # Marcar el memo como absorbido/eliminado lógicamente
        await db.execute(
            text(
                "UPDATE memos SET estado = 'ABSORBIDO', version = version + 1 "
                "WHERE id = :mid"
            ),
            {"mid": source_memo_id},
        )
        logger.info(
            "Marked source memo %s as ABSORBIDO after category %s deletion",
            source_memo_id,
            row_id,
        )

    await db.commit()
    return {"status": "deleted", "id": memo_id}


@router.patch("/agent-outputs/{memo_id}")
async def patch_agent_output(
    memo_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Update fields on an agent output. body: {field: value, ...}

    Para categorías (cat-*) con source_memo_id, sincroniza los cambios de
    nombre/definición de vuelta al memo de origen (sincronización Memo↔Entidad P4).
    """
    from sqlalchemy import text

    parts = memo_id.split("-", 1)
    if len(parts) != 2 or parts[0] not in TABLE_MAP:
        raise HTTPException(400, f"Invalid memo_id format: {memo_id}")
    prefix, row_id = parts
    table, allowed = TABLE_MAP[prefix]

    sets = []
    params = {"id": row_id}
    for key, value in body.items():
        if key in allowed:
            sets.append(f"{key} = :{key}")
            params[key] = value
    if not sets:
        raise HTTPException(400, "No valid fields to update")

    await db.execute(
        text(f"UPDATE {table} SET {', '.join(sets)} WHERE id = :id"), params
    )

    # ── Sync: si es una categoría con source_memo_id, sincronizar al memo ──
    if prefix == "cat" and ("nombre" in body or "definicion" in body):
        source = await db.execute(
            text(
                "SELECT source_memo_id, nombre, definicion FROM categorias WHERE id = :id"
            ),
            {"id": row_id},
        )
        source_row = source.fetchone()
        if source_row and source_row[0]:
            source_memo_id = str(source_row[0])
            cat_def = source_row[2] or ""
            await db.execute(
                text(
                    "UPDATE memos SET contenido = :contenido, version = version + 1 "
                    "WHERE id = :mid"
                ),
                {"contenido": cat_def, "mid": source_memo_id},
            )
            logger.info(
                "Synced source memo %s after category %s update",
                source_memo_id,
                row_id,
            )

    await db.commit()
    return {"status": "updated", "id": memo_id}


@router.patch("/documents/{document_id}/text")
async def patch_document_text(
    document_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Update document text fields stored in metadatos JSONB."""
    import json as _json

    from sqlalchemy import text

    doc = await db.get(Documento, document_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")

    meta = doc.metadatos or {}
    if isinstance(meta, str):
        meta = _json.loads(meta)

    allowed = ["texto_original", "texto_preprocesado"]
    changed = False
    for key in allowed:
        if key in body:
            meta[key] = body[key]
            changed = True

    if not changed:
        raise HTTPException(
            400, "No valid fields. Use texto_original or texto_preprocesado"
        )

    await db.execute(
        text("UPDATE documentos SET metadatos = :meta WHERE id = :did"),
        {"meta": _json.dumps(meta), "did": str(document_id)},
    )
    await db.commit()
    return {"status": "updated", "id": str(document_id)}


def _open_coding_batch_size() -> int:
    """Tamaño de lote de open coding (misma env que workers/heavy/tasks.py).

    El frontend lo usa para saber cuándo debe pedir "N de M documentos
    procesados. ¿Continuar?" sin duplicar el número mágico.
    """
    import os

    try:
        return max(1, int(os.getenv("GT_OPEN_CODING_BATCH_SIZE", "3")))
    except (TypeError, ValueError):
        return 3


async def _get_project_state(db: AsyncSession, project_id: UUID) -> str:
    """Obtiene el estado actual del proyecto desde la DB."""
    from sqlalchemy import text

    row = await db.execute(
        text("SELECT estado FROM proyectos WHERE id = :pid"),
        {"pid": project_id},
    )
    result = row.fetchone()
    return result[0] if result else "collecting"


# Tareas Celery de nivel proyecto registradas en worker-heavy que aceptan
# únicamente (proyecto_id) como primer argumento. Verificado con
# `grep '@app.task(name=...)' workers/heavy/tasks.py`.
# NO incluye tareas que exigen argumentos adicionales (b3_critique_labels,
# f6a_*/f6c_*/f6d_applicability_critic, a01_integrate_paradigm,
# a16_test_interchangeability, f6b_memo_theoretical_tagger, query_lower_level,
# seed_theoretical_codes) ni tareas de las colas fast/nlp.
_PROJECT_LEVEL_TASK_NAMES = frozenset(
    {
        "a3_make_sense",
        "a04_group_constructs",
        "a06_theoretical_sample",
        "a07_build_evidence_map",
        "a14_find_main_concern",
        "a15_core_emergence",
        "b1_compare_incidents",
        "b2_label_groups",
        "core_emergence_pipeline",
        "core_saturation_loop",
        "database_a_pipeline",
        "database_b_pipeline",
        "evaluate_respec_signals",
        "f6d_applicability_engine",
        "final_report",
        "global_saturation_check",
        "invoke_graph",
        "main_concern_pipeline",
        "process_synthesis_agents_b",
        "propose_core_categories",
        "selective_coding_coordinator",
        "selective_reduction_pipeline",
        "synthesize_categories",
        "update_hypotheses",
        "verify_core_pattern",
    }
)

# UI agent ids → Celery task. The open-coding stage uses prompt-level agent ids
# that are not registered Celery task names; without this translation the
# dispatch would be rejected (or silently 200 without executing anything).
# Only agents that map to a real task are listed — the rest are prompt-only and
# must not be launchable on their own.
_AGENT_ID_TO_TASK: dict[str, str] = {
    "fa_population_context": "a3_make_sense",
    "fb_incident_grouper": "b1_compare_incidents",
    "fb_code_generator": "b2_label_groups",
    "fd_category_synthesizer": "synthesize_categories",
    "fd_config_critic": "critique_configuration",
}

# Extra positional args appended after proyecto_id, for tasks whose signature
# needs more than the project id. batch_start=1 is correct for the first batch.
_AGENT_ID_EXTRA_ARGS: dict[str, tuple] = {
    "fd_category_synthesizer": (1,),
    "fd_config_critic": (1,),
}

# Reverse map: which UI agent is in flight for a given Celery task.
_TASK_TO_AGENT_ID: dict[str, str] = {
    task: agent for agent, task in _AGENT_ID_TO_TASK.items()
}

# Orquestadores de fase: no son agentes de la UI, pero sí pintan el spinner de
# la etapa completa mientras están en vuelo.
_PHASE_TASK_TO_STAGE: dict[str, str] = {
    "process_document_agents_a": "data_management",
    "process_synthesis_agents_b": "open_coding",
}


def _celery_task_states(task_ids: list[str]) -> dict[str, str]:
    """Consulta el estado real de cada tarea en el result backend (bloqueante).

    Se ejecuta en un hilo aparte: AsyncResult.status hace I/O contra Redis y no
    debe bloquear el event loop.
    """
    from celery.result import AsyncResult

    states: dict[str, str] = {}
    for tid in task_ids:
        try:
            states[tid] = AsyncResult(tid, app=celery_app).status
        except Exception:
            states[tid] = "UNKNOWN"
    return states


async def _get_or_create_running_run_id(db: AsyncSession, project_id: UUID) -> UUID:
    """Reutiliza el pipeline_run 'running' más reciente o crea uno nuevo."""
    from sqlalchemy import text

    # Un run abandonado no debe absorber el trabajo nuevo (quedaría abierto para
    # siempre y bloquearía memos/borrados). Se reconcilia antes de reutilizarlo.
    await close_idle_runs(db, project_id)

    row = await db.execute(
        text(
            "SELECT id FROM pipeline_runs "
            "WHERE project_id = :pid AND status = 'running' "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"pid": str(project_id)},
    )
    run_id = row.scalar_one_or_none()
    if run_id is not None:
        return run_id

    new_id = uuid4()
    await db.execute(
        text(
            "INSERT INTO pipeline_runs "
            "(id, project_id, status, triggered_by, summary) "
            "VALUES (:id, :pid, 'running', 'manual', '{}'::jsonb)"
        ),
        {"id": new_id, "pid": str(project_id)},
    )
    return new_id


async def _track_pipeline_task(
    db: AsyncSession,
    project_id: UUID,
    document_id: str | None,
    celery_task_id: str,
    task_name: str,
    queue: str,
    doc_estado_before: str | None,
) -> None:
    """Registra la tarea despachada en pipeline_tasks para poder revertirla.

    document_id va NULL para agentes de proyecto (no tocan un documento).
    """
    from sqlalchemy import text

    run_id = await _get_or_create_running_run_id(db, project_id)
    await db.execute(
        text(
            "INSERT INTO pipeline_tasks "
            "(id, run_id, document_id, celery_task_id, task_name, queue, status, "
            " doc_estado_before, segments_before, codes_before) "
            "VALUES (:id, :run_id, :did, :ctid, :tname, :queue, 'queued', "
            " :before, 0, 0)"
        ),
        {
            "id": uuid4(),
            "run_id": run_id,
            # str(None) == 'None' → asyncpg rechaza el literal como UUID.
            "did": str(document_id) if document_id else None,
            "ctid": celery_task_id,
            "tname": task_name,
            "queue": queue,
            "before": doc_estado_before,
        },
    )
    await db.commit()


@router.post("/projects/{project_id}/pipeline/run-agent/{agent_id}")
async def run_single_agent(
    project_id: UUID,
    agent_id: str,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Ejecuta un solo agente por su ID.
    Body opcional: {"document_id": "..."} para agentes per-documento.
    """
    from app.core.celery_app import celery_app

    doc_id = (body or {}).get("document_id")

    # UI agent ids that do not match a registered Celery task name.
    # Per-document agents receive (documento_id, proyecto_id).
    per_doc_task_names = {
        "fa_glaser_data_classifier": "run_glaser_classifier",
        "clasificador_datos": "run_glaser_classifier",
        # "Extraer incidentes" (sidebar y botón por documento): F2.3 runs inside
        # process_document_agents_a, which segments (if needed), classifies
        # segment types and extracts. `fa_document_pattern_extractor` es el id
        # del prompt/agente que hace la extracción baseline; el resto son alias
        # históricos de la UI.
        "fa_document_pattern_extractor": "process_document_agents_a",
        "extract_patterns": "process_document_agents_a",
        "extract_patterns_and_incidents": "process_document_agents_a",
    }

    # Per-document agents need document context
    if doc_id:
        doc = await db.get(Documento, UUID(doc_id))
        if not doc:
            raise HTTPException(404, "Documento no encontrado")

        texto = (
            (doc.metadatos or {}).get("texto_preprocesado")
            or (doc.metadatos or {}).get("texto_extraido")
            or (doc.metadatos or {}).get("texto_original", "")
        )

        # Estado normalizado ANTES del dispatch (para rollback).
        estado_before = (doc.estado or "").strip() or None

        if agent_id == "segmentar_documento":
            from app.agents.transitions import segmenters_available

            # La escalera es classify-first: el clasificador etiqueta el texto y
            # los segmentos heredan esa etiqueta. Segmentar antes dejaría
            # segmentos sin categoría que ninguna etapa posterior reclasifica.
            if not (
                (doc.metadatos or {}).get("glaser_blocks")
                or (doc.metadatos or {}).get("texto_clasificado")
            ):
                raise HTTPException(409, "Clasificá el texto antes de segmentar.")

            if await asyncio.to_thread(segmenters_available):
                task_name = "segmentar_documento"
                queue = "nlp"
                task = celery_app.send_task(
                    task_name,
                    args=[
                        texto,
                        1024,
                        "",
                        "TEXTO",
                        "",
                        doc_id,
                        True,
                    ],  # manual_mode=True
                    queue=queue,
                )
            else:
                # Sin workers de segmentación el segmentador LLM (heavy) hace el
                # trabajo. La clasificación previa se conserva: los segmentos
                # viejos los borra el propio worker antes de insertar los nuevos.
                task_name = "segmentar_documento_llm"
                queue = "heavy"
                task = celery_app.send_task(
                    task_name,
                    args=[doc_id, str(project_id)],
                    queue=queue,
                )
        elif agent_id in ("punctuate_text", "util_punctuator"):
            task_name = "punctuate_text"
            queue = "fast"
            task = celery_app.send_task(
                task_name,
                kwargs={
                    "texto": texto,
                    "max_chars": 10000,
                    "documento_id": doc_id,
                    # Afinidad de caché de prompt: todo el proyecto en la misma réplica.
                    "cache_key": str(project_id),
                },
                queue=queue,
            )
        else:
            task_name = per_doc_task_names.get(agent_id, agent_id)
            queue = "heavy"
            # process_document_agents_a consume segmentos ya clasificados: el
            # estado mínimo es 'segmentado' (la clasificación ocurre antes). En
            # 'clasificado' todavía no hay segmentos y _ensure_segmented no los
            # produce, así que la tarea falla.
            if task_name == "process_document_agents_a" and estado_before not in (
                "segmentado",
                "incidentes_extraidos",
                "procesado",
                "listo",
                "error",
            ):
                raise HTTPException(
                    409,
                    f"Documento en estado '{estado_before}'. "
                    "Segmentá el texto ya clasificado antes de extraer.",
                )
            task = celery_app.send_task(
                task_name,
                args=[doc_id, str(project_id)],
                queue=queue,
            )

        # Tracking: sin esto stop/cancel no pueden revertir el documento.
        await _track_pipeline_task(
            db,
            project_id,
            doc_id,
            task.id,
            task_name,
            queue,
            estado_before,
        )
    else:
        # Project-level agents (cross-doc, synthesizers, etc.).
        # Los ids de agente de la UI no siempre son nombres de tarea Celery:
        # primero traducimos con _AGENT_ID_TO_TASK, y solo después aceptamos
        # un id que ya sea una tarea de proyecto registrada.
        mapped = _AGENT_ID_TO_TASK.get(agent_id)
        if mapped:
            task_name = mapped
            task = celery_app.send_task(
                task_name,
                args=[
                    str(project_id),
                    *_AGENT_ID_EXTRA_ARGS.get(agent_id, ()),
                ],
                queue="heavy",
            )
        else:
            if agent_id not in _PROJECT_LEVEL_TASK_NAMES:
                raise HTTPException(
                    400,
                    f"El agente '{agent_id}' no es una tarea Celery registrada. "
                    "Los agentes de prompt deben ejecutarse vía "
                    f"POST /projects/{project_id}/pipeline/run-stage/{{stage}}.",
                )
            task_name = agent_id
            task = celery_app.send_task(
                task_name,
                args=[str(project_id)],
                queue="heavy",
            )

        # Tracking: permite que /admin/projects/{id}/stop la revoque y que
        # /pipeline/log muestre el agente en vuelo tras un reload.
        await _track_pipeline_task(
            db,
            project_id,
            None,
            task.id,
            task_name,
            "heavy",
            None,
        )

    return {
        "status": "dispatched",
        "agent_id": agent_id,
        "task_name": task_name,
        "task_id": task.id,
    }


@router.patch("/projects/{project_id}/pipeline/pause-config")
async def update_pause_config(
    project_id: UUID,
    config: PauseConfigRequest,
    session: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza el modo de pausa del pipeline: auto (cada 3 docs) o manual."""
    if config.mode not in ("auto", "manual"):
        raise HTTPException(status_code=400, detail="mode must be 'auto' or 'manual'")

    await session.execute(
        text("UPDATE proyectos SET pause_mode = :mode WHERE id = :pid"),
        {"mode": config.mode, "pid": project_id},
    )
    await session.commit()

    return {"status": "ok", "pause_mode": config.mode}


class ContextWindowRequest(BaseModel):
    context_window_real: int = Field(
        ge=10_000,
        le=250_000,
        description="Tokens disponibles para datos (10K-250K)",
    )


@router.patch("/projects/{project_id}/pipeline/context-window")
async def update_context_window(
    project_id: UUID,
    config: ContextWindowRequest,
    session: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Permite al usuario disminuir la ventana de contexto real. Nunca aumentarla."""
    # Validar que no exceda el máximo del modelo
    if config.context_window_real > context_config.MODEL_MAX_CONTEXT_TOKENS:
        raise HTTPException(
            400,
            f"No puede exceder {context_config.MODEL_MAX_CONTEXT_TOKENS} tokens",
        )

    # Obtener proyecto para validar que existe y obtener el valor actual
    result = await session.execute(select(Proyecto).where(Proyecto.id == project_id))
    proyecto = result.scalar_one_or_none()
    if proyecto is None:
        raise HTTPException(404, "Proyecto no encontrado")

    # Validar que no se intente aumentar la ventana (solo disminuir)
    if config.context_window_real > proyecto.context_window_real:
        raise HTTPException(
            400,
            f"Solo se permite disminuir la ventana de contexto. "
            f"Valor actual: {proyecto.context_window_real}",
        )

    await session.execute(
        text("UPDATE proyectos SET context_window_real = :cw WHERE id = :pid"),
        {"cw": config.context_window_real, "pid": project_id},
    )
    await session.commit()

    return {
        "status": "ok",
        "context_window_real": config.context_window_real,
        "model_max_context_tokens": context_config.MODEL_MAX_CONTEXT_TOKENS,
        "effective_window": context_config.effective_window,
        "available_for_data": context_config.available_for_data,
    }
