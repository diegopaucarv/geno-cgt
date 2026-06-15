"""Endpoints HITL (Human In The Loop) para revisión de hipótesis.

Plan §Fase 10: el Coordinator pausa el grafo LangGraph en nodos
de revisión humana. Estos endpoints permiten aceptar, rechazar o
modificar hipótesis candidatas antes de que el pipeline continúe.

Flujo:
  1. GET  /candidates     → listar hipótesis en estado 'candidate'
  2. POST /{id}/accept    → aceptar (status='accepted', confidence=1.0)
  3. POST /{id}/modify    → modificar texto y/o nivel
  4. POST /{id}/reject    → rechazar (status='rejected')
  5. POST /{id}/split     → dividir en hipótesis hijas (Tree of Thoughts)
"""

from __future__ import annotations

from uuid import UUID

from app.db.database import get_db
from app.models.domain.synthesis import Hypothesis
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/hypotheses", tags=["hypotheses"])


# ═══════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════


class HypothesisCandidate(BaseModel):
    id: UUID
    text: str
    level: str  # 'general', 'specific', 'emergent'
    confidence: float
    status: str
    code_id: UUID | None = None
    parent_hypothesis_id: UUID | None = None

    model_config = {"from_attributes": True}


class AcceptRequest(BaseModel):
    justification: str = Field(
        default="", max_length=500, description="Justificación de la decisión"
    )


class ModifyRequest(BaseModel):
    new_text: str = Field(..., min_length=10, max_length=2000)
    new_level: str | None = Field(None, pattern="^(general|specific|emergent)$")
    justification: str = Field(default="", max_length=500)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class SplitRequest(BaseModel):
    children: list[str] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Textos de las hipótesis hijas (2-5)",
    )
    justification: str = Field(default="", max_length=500)


# ═══════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════


@router.get("/candidates", response_model=list[HypothesisCandidate])
async def list_candidates(
    proyecto_id: UUID = Query(..., description="ID del proyecto"),
    status: str = Query("candidate", description="Filtrar por estado"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Lista hipótesis pendientes de revisión humana.

    El Coordinator (LangGraph) pausa el pipeline cuando hay hipótesis
    en estado 'candidate'. Este endpoint alimenta el Hypothesis Panel
    del frontend.
    """
    result = await db.execute(
        select(Hypothesis)
        .where(Hypothesis.project_id == proyecto_id)
        .where(Hypothesis.status == status)
        .order_by(Hypothesis.confidence.desc())
    )
    return result.scalars().all()


@router.post("/{hypothesis_id}/accept")
async def accept_hypothesis(
    hypothesis_id: UUID,
    body: AcceptRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Aceptar una hipótesis candidata.

    Cambia status='accepted', confidence=1.0.
    El Coordinator puede continuar el pipeline al recibir esta señal.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    if hyp.status != "candidate":
        raise HTTPException(
            400, f"Solo se pueden aceptar hipótesis candidatas (actual: {hyp.status})"
        )

    hyp.status = "accepted"
    hyp.confidence = 1.0
    await db.commit()
    await db.refresh(hyp)
    return {"id": str(hyp.id), "status": hyp.status, "confidence": hyp.confidence}


@router.post("/{hypothesis_id}/modify")
async def modify_hypothesis(
    hypothesis_id: UUID,
    body: ModifyRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Modificar una hipótesis candidata (texto y/o nivel).

    La hipótesis modificada vuelve a 'candidate' para que el Testeador
    de memos (A06) la re-evalúe en el siguiente ciclo.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    if hyp.status not in ("candidate", "accepted"):
        raise HTTPException(
            400,
            f"Solo se pueden modificar hipótesis candidatas o aceptadas (actual: {hyp.status})",
        )

    hyp.text = body.new_text
    if body.new_level:
        hyp.level = body.new_level
    hyp.status = "candidate"  # vuelve a cola de revisión
    hyp.confidence = max(
        0.0, hyp.confidence - 0.2
    )  # leve penalización por modificación
    await db.commit()
    await db.refresh(hyp)
    return {"id": str(hyp.id), "status": hyp.status, "text": hyp.text[:100] + "..."}


@router.post("/{hypothesis_id}/reject")
async def reject_hypothesis(
    hypothesis_id: UUID,
    body: RejectRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Rechazar una hipótesis.

    Cambia status='rejected'. El Coordinator excluye hipótesis
    rechazadas de ciclos futuros de B3 y A3.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    hyp.status = "rejected"
    hyp.confidence = 0.0
    await db.commit()
    return {"id": str(hyp.id), "status": hyp.status, "reason": body.reason[:100]}


@router.post("/{hypothesis_id}/split", status_code=201)
async def split_hypothesis(
    hypothesis_id: UUID,
    body: SplitRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Dividir una hipótesis en hipótesis hijas (Tree of Thoughts).

    La hipótesis original se marca como 'split'. Las hijas heredan
    el project_id, code_id y parent_hypothesis_id.

    Útil cuando una hipótesis es demasiado amplia y el investigador
    identifica sub-hipótesis más precisas.
    """
    hyp = await db.get(Hypothesis, hypothesis_id)
    if not hyp:
        raise HTTPException(404, "Hipótesis no encontrada")

    if hyp.status == "rejected":
        raise HTTPException(400, "No se puede dividir una hipótesis rechazada")

    # Marcar original como dividida
    hyp.status = "split"

    # Crear hijas
    children = []
    for child_text in body.children:
        child = Hypothesis(
            project_id=hyp.project_id,
            code_id=hyp.code_id,
            text=child_text,
            level=hyp.level,
            confidence=0.5,
            status="candidate",
            parent_hypothesis_id=hypothesis_id,
        )
        db.add(child)
        children.append(child)

    await db.commit()
    return {
        "parent_id": str(hyp.id),
        "parent_status": hyp.status,
        "children_created": len(children),
    }
