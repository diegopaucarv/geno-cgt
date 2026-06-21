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


# ═══════════════════════════════════════════════════════════════════════
# Open Coding HITL Gate — unified concern / population / categories gate
# ═══════════════════════════════════════════════════════════════════════


class ConcernCandidate(BaseModel):
    """Gerund concern candidate surfaced by the concern proposer agent."""

    label: str
    supporting_codes: list[str] = Field(default_factory=list)
    rationale: str = ""


class PopulationProposal(BaseModel):
    """Population description proposal from the population context builder."""

    description: str
    source_batch: int


class UnifiedCategory(BaseModel):
    """Category unified for the open coding gate, with core-candidate flag."""

    id: UUID
    label: str
    definition: str
    is_core_candidate: bool


class UnifiedHypothesis(BaseModel):
    """Hypothesis unified for the open coding gate, with concern relevance."""

    id: UUID
    text: str
    concern_relevance: str = "INDIRECT"  # "DIRECT" | "INDIRECT"
    is_core_candidate: bool = False


class OpenCodingHITLStatusResponse(BaseModel):
    """Full status of the open coding HITL gate for the frontend panel."""

    docs_processed: int
    total_docs: int
    batch_number: int
    concern_candidates: list[ConcernCandidate]
    population_proposals: list[PopulationProposal]
    unified_categories: list[UnifiedCategory]
    unified_hypotheses: list[UnifiedHypothesis]
    chosen_concern: str | None
    chosen_population: str | None
    can_proceed: bool


class OpenCodingHITLDecision(BaseModel):
    """Body for POST /hitl/open-coding/decide — researcher's HITL decision."""

    chosen_concern: str = Field(..., min_length=1, max_length=255)
    chosen_population: str = Field(..., min_length=1, max_length=2000)
    core_category_ids: list[UUID] = Field(default_factory=list)
    confirmed: bool = False
    researcher_note: str = Field(default="", max_length=2000)


class OpenCodingHITLDecisionResponse(BaseModel):
    """Response after the researcher submits the open coding HITL decision."""

    status: str
    chosen_concern: str
    chosen_population: str
    core_categories_set: int
    confirmed: bool


class PauseConfigRequest(BaseModel):
    """Body for PATCH /pipeline/pause-config — update pipeline pause mode."""

    mode: str = Field(..., pattern="^(auto|manual)$")
    """'auto' pauses automatically every 3 docs; 'manual' lets the user decide."""
