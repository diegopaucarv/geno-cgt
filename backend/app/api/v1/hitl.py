"""HITL decision endpoint — gates del pipeline selectivo.

Los workers del pipeline selectivo insertan filas en hitl_decisions
cuando llegan a un gate HITL. El frontend consulta las pendientes
y el investigador decide ACCEPT/MODIFY/REJECT.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.schemas.hitl import (
    HitlDecisionRequest,
    HitlDecisionResponse,
    HitlPendingItem,
)
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["hitl"])


@router.get("/projects/{project_id}/hitl/{gate_name}/detail")
async def get_hitl_detail(
    project_id: UUID,
    gate_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Obtiene la decisión HITL completa (proposal + critic_verdict) para mostrar en el modal."""
    row = await db.execute(
        text(
            "SELECT id, gate_name, proposal, critic_verdict, status, creado_en "
            "FROM hitl_decisions "
            "WHERE project_id = :pid AND gate_name = :gate "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"pid": project_id, "gate": gate_name},
    )
    decision_row = row.fetchone()
    if not decision_row:
        raise HTTPException(404, f"No decision found for gate '{gate_name}'")

    return {
        "id": str(decision_row[0]),
        "gate_name": decision_row[1],
        "proposal": decision_row[2] if isinstance(decision_row[2], dict) else {},
        "critic_verdict": decision_row[3] if isinstance(decision_row[3], dict) else {},
        "status": decision_row[4],
        "created_at": str(decision_row[5]),
    }


@router.get("/projects/{project_id}/hitl/pending")
async def get_pending_decisions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[HitlPendingItem]:
    """Devuelve las decisiones HITL pendientes para un proyecto."""
    rows = await db.execute(
        text(
            "SELECT id, gate_name, proposal, critic_verdict, creado_en "
            "FROM hitl_decisions "
            "WHERE project_id = :pid AND status = 'pending' "
            "ORDER BY creado_en ASC"
        ),
        {"pid": project_id},
    )
    results = []
    for row in rows:
        proposal = row[2] if isinstance(row[2], dict) else {}
        critic = row[3] if isinstance(row[3], dict) else {}
        results.append(
            HitlPendingItem(
                id=row[0],
                gate_name=row[1],
                proposal_summary=proposal.get("core_concern", "")
                or proposal.get("rationale", "")[:200],
                critic_verdict=critic.get("verdict", "SAT"),
                created_at=row[4],
            )
        )
    return results


@router.post(
    "/projects/{project_id}/hitl/{gate_name}/decide",
    response_model=HitlDecisionResponse,
)
async def decide_hitl(
    project_id: UUID,
    gate_name: str,
    body: HitlDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    El investigador decide sobre una propuesta en un gate HITL.

    - ACCEPT → la decisión se marca como aceptada. El coordinator
      (cuando exista) detectará el cambio y avanzará el pipeline.
    - MODIFY → se guarda el feedback. El coordinator re-ejecutará
      el proposer con las instrucciones del investigador.
    - REJECT → se archiva la decisión con nota metodológica.
    """
    # 1. Buscar la decisión pendiente más reciente para este gate
    row = await db.execute(
        text(
            "SELECT id FROM hitl_decisions "
            "WHERE project_id = :pid AND gate_name = :gate AND status = 'pending' "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"pid": project_id, "gate": gate_name},
    )
    decision_row = row.fetchone()
    if not decision_row:
        raise HTTPException(404, f"No pending decision for gate '{gate_name}'")

    decision_id = decision_row[0]

    # 2. Actualizar la decisión
    new_status = (
        "accepted"
        if body.decision == "accept"
        else "modified"
        if body.decision == "modify"
        else "rejected"
    )
    now = datetime.now(timezone.utc)

    await db.execute(
        text(
            "UPDATE hitl_decisions SET "
            "status = :status, "
            "researcher_decision = :dec, "
            "researcher_note = :note, "
            "researcher_feedback = :fb, "
            "decided_at = :now "
            "WHERE id = :did"
        ),
        {
            "status": new_status,
            "dec": body.decision,
            "note": body.note,
            "fb": body.feedback,
            "now": now,
            "did": decision_id,
        },
    )
    await db.commit()

    # 3. Re-disparar coordinator para continuar el pipeline
    if body.decision in ("accept", "modify"):
        try:
            from app.core.celery_app import celery_app

            celery_app.send_task(
                "selective_coding_coordinator",
                args=[str(project_id)],
                queue="heavy",
            )
            logger.info(
                "Coordinator re-dispatched for project=%s after %s decision",
                project_id,
                body.decision,
            )
        except Exception as e:
            logger.warning("Failed to re-dispatch coordinator: %s", e)

    logger.info(
        "HITL decision: gate=%s decision=%s by user=%s",
        gate_name,
        body.decision,
        current_user.id,
    )

    return HitlDecisionResponse(
        id=decision_id,
        project_id=project_id,
        gate_name=gate_name,
        status=new_status,
        researcher_decision=body.decision,
        researcher_note=body.note,
        decided_at=now,
    )
