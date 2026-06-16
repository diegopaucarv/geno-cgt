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
        task = celery_app.send_task(
            "a14_find_main_concern",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "selective":
        task = celery_app.send_task(
            "trigger_selective_elaboration",
            args=[str(project_id)],
            queue="heavy",
        )
        result["task_ids"].append(task.id)
        result["status"] = "dispatched"

    elif stage_name == "saturation":
        # Saturation runs via analysis endpoint — no Celery task to dispatch
        result["status"] = "ready"
        result["note"] = "Use GET /projects/{pid}/analysis/saturation-gaps"

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
            "agents_done": doc.estado == "listo" and n_codes > 0,
        }

        # Determinar qué falta
        if not has_text:
            next_action = "extract_text"
        elif not n_segs:
            next_action = "segment"
        elif not n_codes:
            next_action = "run_agents"
        elif doc.estado == "listo":
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

    # Resumen
    docs_need_segment = sum(1 for d in doc_logs if d["next_action"] == "segment")
    docs_need_agents = sum(1 for d in doc_logs if d["next_action"] == "run_agents")
    docs_done = sum(1 for d in doc_logs if d["next_action"] == "done")

    return {
        "project_id": str(project_id),
        "documents": doc_logs,
        "summary": {
            "total": len(docs),
            "need_segment": docs_need_segment,
            "need_agents": docs_need_agents,
            "done": docs_done,
            "categories": cat_count,
            "playground_ready": cat_count > 0,
        },
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
