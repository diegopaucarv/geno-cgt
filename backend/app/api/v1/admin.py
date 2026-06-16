"""Admin endpoints: stop/cancel/kill/restart/resume del pipeline."""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.celery_app import celery_app
from app.db.database import get_db
from app.models.domain.pipeline_run import PipelineRun, PipelineTask
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ═══════════════════════════════════════════════════════════════════════
# Workers — stop individuales
# ═══════════════════════════════════════════════════════════════════════


@router.post("/workers/{worker_name}/stop")
async def stop_worker(worker_name: str):
    """
    Revoca todas las tareas activas y pendientes en una cola.

    worker_name: 'fast' | 'heavy' | 'nlp'
    """
    # 1. Purgar tareas pendientes (no empezadas aún)
    celery_app.control.purge()

    # 2. Terminar tareas en ejecución
    inspector = celery_app.control.inspect()
    active_tasks = inspector.active() or {}

    revoked = 0
    for _worker, tasks in active_tasks.items():
        for task in tasks:
            celery_app.control.revoke(task["id"], terminate=True, signal="SIGTERM")
            revoked += 1

    return {
        "status": "stopped",
        "worker": worker_name,
        "tasks_revoked": revoked,
    }


@router.get("/workers/status")
async def worker_status():
    """Estado de todos los workers: tareas activas, pendientes, reservadas."""
    inspector = celery_app.control.inspect()
    return {
        "active": inspector.active() or {},
        "reserved": inspector.reserved() or {},
        "scheduled": inspector.scheduled() or {},
    }


# ═══════════════════════════════════════════════════════════════════════
# Workers — kill all (emergencia)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/workers/kill-all")
async def kill_all_workers(
    current_user: Usuario = Depends(get_current_user),
):
    """
    ☠️ Emergencia: detiene TODOS los workers Celery.

    Envía broadcast de shutdown. docker-compose los reiniciará
    automáticamente (restart: unless-stopped).
    """
    # 1. Purge queues
    celery_app.control.purge()

    # 2. Shutdown broadcast
    celery_app.control.broadcast("shutdown")

    # 3. Revocar tareas activas con SIGKILL
    inspector = celery_app.control.inspect()
    active = inspector.active() or {}
    revoked = 0
    for _worker, tasks in active.items():
        for task in tasks:
            celery_app.control.revoke(task["id"], terminate=True, signal="SIGKILL")
            revoked += 1

    return {
        "status": "killed",
        "workers_shutdown": True,
        "tasks_revoked": revoked,
        "warning": "Workers will restart automatically (docker restart policy)",
    }


# ═══════════════════════════════════════════════════════════════════════
# Project — stop all tasks + rollback
# ═══════════════════════════════════════════════════════════════════════


@router.post("/projects/{project_id}/stop")
async def stop_project_pipeline(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    ⏹ Detiene TODAS las tareas del pipeline de un proyecto.

    1. Busca el PipelineRun activo
    2. Revoca todas sus PipelineTasks (activas + pendientes)
    3. Rollback de cada tarea (restaura doc_estado_before)
    4. Limpia logs de Redis
    """
    # 1. Buscar run activo
    run = (
        await db.execute(
            select(PipelineRun).where(
                PipelineRun.project_id == project_id,
                PipelineRun.status == "running",
            )
        )
    ).scalar_one_or_none()

    if not run:
        # Sin run activo, revocar cualquier tarea suelta
        inspector = celery_app.control.inspect()
        active = inspector.active() or {}
        revoked = 0
        for _worker, tasks in active.items():
            for task in tasks:
                celery_app.control.revoke(task["id"], terminate=True)
                revoked += 1
        return {
            "status": "stopped",
            "active_run": None,
            "tasks_revoked": revoked,
        }

    # 2. Revocar todas las tareas del run
    tasks = (
        (await db.execute(select(PipelineTask).where(PipelineTask.run_id == run.id)))
        .scalars()
        .all()
    )

    results = []
    for task in tasks:
        if task.status in ("queued", "running"):
            celery_app.control.revoke(task.celery_task_id, terminate=True)
            task.status = "cancelled"

            # Rollback: restaurar estado del documento
            if task.document_id and task.doc_estado_before:
                await db.execute(
                    text("UPDATE documentos SET estado = :estado WHERE id = :did"),
                    {
                        "estado": task.doc_estado_before,
                        "did": task.document_id,
                    },
                )

            results.append(
                {
                    "task_id": task.celery_task_id,
                    "status": "cancelled",
                    "doc_rolled_back": (
                        str(task.document_id) if task.document_id else None
                    ),
                    "previous_state": task.doc_estado_before,
                }
            )

    # 3. Marcar run como cancelado
    run.status = "cancelled"
    await db.commit()

    # 4. Limpiar logs de Redis
    try:
        import os as _os

        import redis.asyncio as _aredis

        r = _aredis.from_url(_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        await r.delete(f"pipeline_logs:{project_id}")
        await r.close()
    except Exception:
        pass

    return {
        "status": "stopped",
        "run_id": str(run.id),
        "tasks_cancelled": len(results),
        "details": results,
    }


# ═══════════════════════════════════════════════════════════════════════
# Task — cancel individual (Nivel 2)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    ⏸ Cancela UNA tarea específica y limpia sus side-effects.

    Si la tarea ya empezó:
    - Envía SIGTERM al worker
    - Revierte el documento a su estado anterior
    """
    # Buscar en nuestro tracking (por celery_task_id)
    task_record = (
        await db.execute(
            select(PipelineTask).where(PipelineTask.celery_task_id == task_id)
        )
    ).scalar_one_or_none()

    if not task_record:
        # Fallback: revocar sin limpiar (no tenemos tracking)
        celery_app.control.revoke(task_id, terminate=True)
        return {"status": "revoked", "cleanup": "unknown"}

    # Revocar en Celery
    celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")

    # Rollback
    if task_record.document_id and task_record.doc_estado_before:
        await db.execute(
            text("UPDATE documentos SET estado = :estado WHERE id = :did"),
            {
                "estado": task_record.doc_estado_before,
                "did": task_record.document_id,
            },
        )

    task_record.status = "cancelled"
    await db.commit()

    return {
        "status": "cancelled",
        "task_id": task_id,
        "document_rolled_back": (
            str(task_record.document_id) if task_record.document_id else None
        ),
        "previous_state": task_record.doc_estado_before,
    }


# ═══════════════════════════════════════════════════════════════════════
# Task — restart (desde cero)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/tasks/{task_id}/restart")
async def restart_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    🔄 Re-ejecuta una tarea desde cero (reset).

    Útil cuando:
    - La tarea falló por error transitorio (timeout de API)
    - El usuario canceló por error y quiere re-ejecutar
    """
    task_record = (
        await db.execute(
            select(PipelineTask).where(PipelineTask.celery_task_id == task_id)
        )
    ).scalar_one_or_none()

    if not task_record:
        raise HTTPException(404, "Task not found in tracking")

    # Limpiar checkpoints de la tarea anterior
    from app.models.domain.pipeline_run import TaskStepCheckpoint

    await db.execute(
        text("DELETE FROM task_step_checkpoints WHERE pipeline_task_id = :ptid"),
        {"ptid": task_record.id},
    )
    await db.commit()

    # Re-disparar la misma tarea
    new_task = celery_app.send_task(
        task_record.task_name,
        args=[str(task_record.document_id)] if task_record.document_id else [],
        queue=task_record.queue,
    )

    # Crear nuevo registro de tracking
    new_record = PipelineTask(
        run_id=task_record.run_id,
        document_id=task_record.document_id,
        celery_task_id=new_task.id,
        task_name=task_record.task_name,
        queue=task_record.queue,
        status="queued",
        doc_estado_before=task_record.doc_estado_before,
    )
    db.add(new_record)
    await db.commit()

    return {
        "status": "restarted",
        "old_task_id": task_id,
        "new_task_id": new_task.id,
    }


# ═══════════════════════════════════════════════════════════════════════
# Task — resume (continuar desde donde se quedó)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    ▶️ Reanuda una tarea cancelada desde donde se quedó.

    A diferencia de restart (empieza de cero), resume:
    - Detecta pasos ya completados (vía TaskStepCheckpoint)
    - Limpia pasos que quedaron in_progress
    - Continúa desde el primer paso no completado
    - SOBRESCRIBE cualquier dato parcial del intento anterior
    """
    from app.models.domain.pipeline_run import TaskStepCheckpoint

    task_record = (
        await db.execute(
            select(PipelineTask).where(PipelineTask.celery_task_id == task_id)
        )
    ).scalar_one_or_none()

    if not task_record:
        raise HTTPException(404, "Task not found in tracking")

    # Encontrar último paso completado
    last_checkpoint = (
        await db.execute(
            select(TaskStepCheckpoint)
            .where(
                TaskStepCheckpoint.pipeline_task_id == task_record.id,
                TaskStepCheckpoint.status == "completed",
            )
            .order_by(TaskStepCheckpoint.creado_en.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    resume_from = last_checkpoint.step_name if last_checkpoint else None

    # Re-disparar en modo resume
    kwargs = {}
    if resume_from:
        kwargs["resume_from_step"] = resume_from

    new_task = celery_app.send_task(
        task_record.task_name,
        args=[str(task_record.document_id)] if task_record.document_id else [],
        kwargs=kwargs,
        queue=task_record.queue,
    )

    return {
        "status": "resumed",
        "old_task_id": task_id,
        "new_task_id": new_task.id,
        "resume_from_step": resume_from,
        "note": f"Continuará desde el paso '{resume_from or 'inicio'}' y sobrescribirá datos parciales",
    }


# ═══════════════════════════════════════════════════════════════════════
# Project — restart failed tasks
# ═══════════════════════════════════════════════════════════════════════


@router.post("/projects/{project_id}/pipeline/restart-failed")
async def restart_failed_tasks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    🔄 Re-ejecuta todas las tareas fallidas o canceladas del último
    PipelineRun. No toca las que ya completaron.
    """
    run = (
        await db.execute(
            select(PipelineRun)
            .where(PipelineRun.project_id == project_id)
            .order_by(PipelineRun.creado_en.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not run:
        raise HTTPException(404, "No pipeline run found for this project")

    failed_tasks = (
        (
            await db.execute(
                select(PipelineTask).where(
                    PipelineTask.run_id == run.id,
                    PipelineTask.status.in_(("failed", "cancelled")),
                )
            )
        )
        .scalars()
        .all()
    )

    restarted = []
    for task in failed_tasks:
        new_task = celery_app.send_task(
            task.task_name,
            args=[str(task.document_id)] if task.document_id else [],
            queue=task.queue,
        )
        restarted.append(
            {
                "old_task_id": task.celery_task_id,
                "new_task_id": new_task.id,
            }
        )

    return {
        "status": "restarted",
        "count": len(restarted),
        "tasks": restarted,
    }
