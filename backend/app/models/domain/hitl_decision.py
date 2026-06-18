"""HitlDecision — modelo para gates Human-in-the-Loop del pipeline selectivo."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class HitlDecision(Base, TimestampMixin):
    """Una decisión pendiente del investigador en un gate HITL."""

    __tablename__ = "hitl_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    gate_name: Mapped[str] = mapped_column(String(100))
    # "pattern_of_interest" | "core_category" | "selective_reduction"
    # | "core_saturation" | "database_a" | "database_b" | "global_saturation"

    proposal: Mapped[dict] = mapped_column(JSONB)
    # Output del proposer (varía según el gate)

    critic_verdict: Mapped[dict] = mapped_column(JSONB)
    # Output del critic: {verdict: "SAT"|"MOD"|"FORCED", rationale, suggestions}

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # "pending" | "accepted" | "modified" | "rejected"

    researcher_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "accept" | "modify" | "reject"

    researcher_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nota del investigador (siempre presente)

    researcher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Feedback para re-ejecutar el proposer (solo si MODIFY)

    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
