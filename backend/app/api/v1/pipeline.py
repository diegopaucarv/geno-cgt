"""Pipeline execution endpoints — dispara stages y devuelve task_ids para polling."""

from uuid import UUID

from app.core.celery_app import celery_app
from app.db.database import get_db
from app.models.domain.document import Documento
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


@router.post("/projects/{project_id}/pipeline/run-stage/{stage_name}")
async def run_pipeline_stage(
    project_id: UUID,
    stage_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Dispara una etapa del pipeline y devuelve los task_ids para polling.

    Stages: upload, precoding, open_coding, cross_doc, main_concern,
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
                    (doc.metadatos or {}).get("texto_extraido", ""),
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
        for doc in docs:
            if doc.estado in ("crudo", "segmentando", "segmentado"):
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
        task = celery_app.send_task(
            "process_synthesis_agents_b",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "main_concern":
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
                "need_agents": 0,
                "done": 0,
                "failed": 0,
                "categories": 0,
                "playground_ready": False,
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
        has_text = bool((doc.metadatos or {}).get("texto_extraido", ""))

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
        }

        # Determinar qué falta
        if doc.estado == "error":
            next_action = "error"
        elif not has_text:
            next_action = "extract_text"
        elif not n_segs:
            next_action = "segment"
        elif not n_codes:
            next_action = "run_agents"
        elif doc.estado == "listo":
            next_action = "run_synthesis"
        elif doc.estado == "sintetizado":
            next_action = "done"
        else:
            next_action = "run_agents"

        doc_logs.append(
            {
                "document_id": did,
                "filename": doc.original_filename,
                "estado": doc.estado,
                "steps": steps_done,
                "segments_count": n_segs,
                "codes_count": n_codes,
                "next_action": next_action,
            }
        )

    # Resumen con nuevos estados
    docs_need_segment = sum(1 for d in doc_logs if d["next_action"] == "segment")
    docs_need_agents = sum(1 for d in doc_logs if d["next_action"] == "run_agents")
    docs_need_synthesis = sum(
        1 for d in doc_logs if d["next_action"] == "run_synthesis"
    )
    docs_done = sum(1 for d in doc_logs if d["next_action"] == "done")
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

    return {
        "project_id": str(project_id),
        "documents": doc_logs,
        "summary": {
            "total": len(docs),
            "need_segment": docs_need_segment,
            "need_agents": docs_need_agents,
            "need_synthesis": docs_need_synthesis,
            "sintetizados": docs_sintetizados,
            "done": docs_done,
            "failed": docs_failed,
            "failed_tasks": failed_tasks,
            "errors": error_list,
            "categories": cat_count,
            "project_state": await _get_project_state(db, project_id),
            "playground_ready": docs_sintetizados == len(docs) and cat_count > 0,
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
            "researcher_decision, researcher_note, decidido_en "
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
        text("SELECT COUNT(*) FROM hipotesis WHERE proyecto_id = :pid"),
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
        "main_concern": "pending",
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


@router.post("/projects/{project_id}/pipeline/run")
async def run_pipeline_orchestrated(
    project_id: UUID,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Orchestrator único del pipeline.
    Recibe {"force": false} y determina qué pasos ejecutar
    basándose en el estado REAL de la DB (segmentos, códigos).

    Retorna inmediatamente con task_ids. El frontend hace polling
    de /pipeline/tail y /pipeline/log para seguir el progreso.
    """
    from sqlalchemy import text

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

    # ── 2. Para cada doc, determinar qué falta mirando la DB real ──
    doc_ids = [d.id for d in docs]

    # Segmentos por doc
    seg_counts = {}
    if doc_ids:
        seg_result = await db.execute(
            text(
                "SELECT documento_id, COUNT(*) FROM segmentos WHERE documento_id = ANY(:ids) GROUP BY documento_id"
            ),
            {"ids": doc_ids},
        )
        for row in seg_result:
            seg_counts[str(row[0])] = row[1]

    # Códigos por doc (via segmentos)
    code_counts = {}
    if doc_ids:
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

    # ── 3. Clasificar docs ──
    need_segment = []
    need_agents = []
    already_done = []

    for doc in docs:
        did = str(doc.id)
        n_segs = seg_counts.get(did, 0)
        n_codes = code_counts.get(did, 0)

        if force:
            if n_segs == 0:
                need_segment.append(doc)
            else:
                need_agents.append(doc)
        else:
            if n_segs == 0:
                need_segment.append(doc)
            elif n_codes == 0:
                need_agents.append(doc)
            else:
                already_done.append(doc)

    # ── 4. Delegar al Orchestrator centralizado ──
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


@router.delete("/agent-outputs/{memo_id}")
async def delete_agent_output(
    memo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Delete an agent output. memo_id format: {prefix}-{uuid} (e.g. pc-xxx, dp-xxx, cat-xxx)"""
    from sqlalchemy import text

    parts = memo_id.split("-", 1)
    if len(parts) != 2 or parts[0] not in TABLE_MAP:
        raise HTTPException(400, f"Invalid memo_id format: {memo_id}")
    prefix, row_id = parts
    table, _ = TABLE_MAP[prefix]
    await db.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id})
    await db.commit()
    return {"status": "deleted", "id": memo_id}


@router.patch("/agent-outputs/{memo_id}")
async def patch_agent_output(
    memo_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Update fields on an agent output. body: {field: value, ...}"""
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
    await db.commit()
    return {"status": "updated", "id": memo_id}


@router.patch("/documents/{document_id}/text")
async def patch_document_text(
    document_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Update document text fields (texto_extraido, original_filename)."""
    from sqlalchemy import text

    allowed = ["texto_extraido", "original_filename"]
    sets = []
    params = {"id": str(document_id)}
    for key, value in body.items():
        if key in allowed:
            sets.append(f"{key} = :{key}")
            params[key] = value
    if not sets:
        raise HTTPException(400, "No valid fields")

    await db.execute(
        text(f"UPDATE documentos SET {', '.join(sets)} WHERE id = :id"), params
    )
    await db.commit()
    return {"status": "updated", "id": str(document_id)}


async def _get_project_state(db: AsyncSession, project_id: UUID) -> str:
    """Obtiene el estado actual del proyecto desde la DB."""
    from sqlalchemy import text

    row = await db.execute(
        text("SELECT estado FROM proyectos WHERE id = :pid"),
        {"pid": project_id},
    )
    result = row.fetchone()
    return result[0] if result else "collecting"
