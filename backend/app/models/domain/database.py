"""DatabaseNode + DatabaseEdge — modelo relacional para Database A/B."""

from __future__ import annotations

import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class DatabaseNode(Base, TimestampMixin):
    """Nodo plano del modelo teórico (Database A)."""

    __tablename__ = "database_nodes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categorias.id"), nullable=True
    )

    label: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(50))
    # PROCESS | ACTOR | CONDITION | CONSEQUENCE | CONTEXT | STRATEGY

    definition: Mapped[str] = mapped_column(Text)
    is_core: Mapped[bool] = mapped_column(default=False)


class DatabaseEdge(Base, TimestampMixin):
    """Edge/relación del modelo teórico (Database B)."""

    __tablename__ = "database_edges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    source_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("database_nodes.id"))
    target_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("database_nodes.id"))

    relationship_type: Mapped[str] = mapped_column(Text)
    # Free-text theoretical description (previously enum-based, now description-driven)

    description: Mapped[str] = mapped_column(Text, default="")
    # The complete free-text relationship description from the proposer

    evidence: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(20), default="unidirectional")
    strength: Mapped[str] = mapped_column(String(20), default="moderate")
    # weak | moderate | strong
