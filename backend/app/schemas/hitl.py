"""Schemas Pydantic para el endpoint HITL."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HitlDecisionRequest(BaseModel):
    """Body del endpoint POST /hitl/{gate}/decide."""

    decision: str = Field(..., pattern="^(accept|modify|reject)$")
    note: str = Field(default="", max_length=2000)
    feedback: str | None = Field(default=None, max_length=2000)
    # feedback solo se usa si decision == "modify"


class HitlDecisionResponse(BaseModel):
    """Respuesta con la decisión tomada."""

    id: UUID
    project_id: UUID
    gate_name: str
    status: str
    researcher_decision: str | None
    researcher_note: str | None
    decided_at: datetime | None

    model_config = {"from_attributes": True}


class HitlPendingItem(BaseModel):
    """Item en la lista de decisiones pendientes."""

    id: UUID
    gate_name: str
    proposal_summary: str  # extracto de la propuesta para el frontend
    critic_verdict: str  # e.g., "2/4 strong", "NO_FEEDBACK" — derived from observations
    created_at: datetime

    model_config = {"from_attributes": True}
