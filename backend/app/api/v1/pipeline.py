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
        import redis.asyncio as _aredis, os as _os
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
            text("SELECT documento_id, COUNT(*) FROM segmentos WHERE documento_id = ANY(:ids) GROUP BY documento_id"),
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
                need_agents.append(doc)
            else:
                need_agents.append(doc)
        else:
            if n_segs == 0:
                need_segment.append(doc)
                need_agents.append(doc)
            elif n_codes == 0:
                need_agents.append(doc)
            else:
                already_done.append(doc)
    
    # ── 4. Disparar workers ──
    from app.core.celery_app import celery_app
    
    task_ids = {"segment": [], "agents": []}
    
    # Segmentación (una tarea por doc que lo necesita)
    for doc in need_segment:
        texto = (doc.metadatos or {}).get("texto_extraido", "")
        if texto:
            task = celery_app.send_task(
                "segmentar_documento",
                args=[texto, 1024, doc.original_filename, "TEXTO", "", str(doc.id)],
                queue="nlp",
            )
            task_ids["segment"].append({"doc_id": str(doc.id), "task_id": task.id})
    
    # Agentes (una tarea por doc que lo necesita)
    for doc in need_agents:
        task = celery_app.send_task(
            "process_document_agents_a",
            args=[str(doc.id), str(project_id)],
            queue="heavy",
        )
        task_ids["agents"].append({"doc_id": str(doc.id), "task_id": task.id})
    
    return {
        "status": "dispatched",
        "project_id": str(project_id),
        "summary": {
            "need_segment": len(need_segment),
            "need_agents": len(need_agents),
            "already_done": len(already_done),
            "total": len(docs),
        },
        "task_ids": task_ids,
        "message": (
            f"Disparado: {len(need_segment)} segmentaciones, "
            f"{len(need_agents)} agentes. "
            f"{len(already_done)} docs ya completos."
        ),
    }


@router.get("/projects/{project_id}/pipeline/tail")
async def tail_pipeline_logs(
    project_id: UUID,
    since: float = 0,
):
    """Devuelve logs del pipeline en tiempo real desde Redis."""
    import json as _json, os as _os
    import redis.asyncio as _aredis

    redis_url = _os.getenv("REDIS_URL", "redis://redis:6379/0").replace("redis://", "redis://default@")
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

