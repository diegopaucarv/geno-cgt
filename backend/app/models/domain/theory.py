# backend/app/models/domain/theory.py
"""
Theoretical Playground — Fase 6b.

Tablas para el ecosistema conceptual: códigos teóricos, relaciones elaboradas,
historial de definiciones, memos de elaboración, y layout del ecosistema.
"""

from __future__ import annotations

import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ═══════════════════════════════════════════════════════════════════
# T01 — Códigos teóricos (built-in + user-defined)
# ═══════════════════════════════════════════════════════════════════


class TheoreticalCode(Base, TimestampMixin):
    __tablename__ = "theoretical_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proyectos.id"), nullable=True
    )
    # NULL = built-in (global). NOT NULL = user-defined.

    name: Mapped[str] = mapped_column(String(200))
    family: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    glaserian: Mapped[bool] = mapped_column(Boolean, default=False)
    user_defined: Mapped[bool] = mapped_column(Boolean, default=False)

    evaluation_logic: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    compatible_with: Mapped[list] = mapped_column(JSONB, default=list)
    layer: Mapped[str] = mapped_column(String(50))
    visualization_hint: Mapped[str] = mapped_column(String(50), default="tendril")

    # Relaciones
    relationships = relationship(
        "ConceptualRelationship", back_populates="theoretical_code"
    )


# ═══════════════════════════════════════════════════════════════════
# T02 — Historial de definiciones de categorías
# ═══════════════════════════════════════════════════════════════════


class CategoryDefinitionVersion(Base, TimestampMixin):
    __tablename__ = "category_definition_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categorias.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    version: Mapped[int] = mapped_column(Integer)

    name_at_version: Mapped[str] = mapped_column(String(200))
    definition_at_version: Mapped[str] = mapped_column(Text)
    properties_at_version: Mapped[dict] = mapped_column(JSONB, default=dict)
    incident_count_at_version: Mapped[int] = mapped_column(Integer, default=0)

    trigger: Mapped[str] = mapped_column(String(50))
    # "manual_edit" | "ghost_absorbed" | "relationship_elaborated" | "rename_applied"
    # | "incident_converged" | "incident_diverged_property" | "incident_diverged_dimension"
    trigger_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    category = relationship("Categoria", back_populates="definition_versions")


# ═══════════════════════════════════════════════════════════════════
# T03 — Relaciones conceptuales elaboradas
# ═══════════════════════════════════════════════════════════════════


class ConceptualRelationship(Base, TimestampMixin):
    __tablename__ = "conceptual_relationships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    category_ids: Mapped[list] = mapped_column(JSONB, default=list)
    theoretical_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("theoretical_codes.id")
    )
    researcher_question: Mapped[str] = mapped_column(Text)

    elaboration_status: Mapped[str] = mapped_column(String(50), default="emerging")
    direction: Mapped[str | None] = mapped_column(String(100), nullable=True)

    converging_incident_ids: Mapped[list] = mapped_column(JSONB, default=list)
    converging_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    diverging_incident_ids: Mapped[list] = mapped_column(JSONB, default=list)
    diverging_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    divergence_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    origin_memo_ids: Mapped[list] = mapped_column(JSONB, default=list)
    origin_hypothesis_ids: Mapped[list] = mapped_column(JSONB, default=list)

    conceptual_fit: Mapped[float] = mapped_column(Float, default=0.0)
    layer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position_tension: Mapped[float] = mapped_column(Float, default=0.0)

    # Relaciones
    theoretical_code = relationship("TheoreticalCode", back_populates="relationships")


# ═══════════════════════════════════════════════════════════════════
# T04 — Memos de elaboración (clasificación de Glaser)
# ═══════════════════════════════════════════════════════════════════


class ElaborationMemo(Base, TimestampMixin):
    __tablename__ = "elaboration_memos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    elaboration_type: Mapped[str] = mapped_column(String(50))
    # "relationship_proposed" | "divergence_expanded" | "ghost_absorbed"
    # | "rename_applied" | "definition_expanded" | "sampling_recommended"

    relationship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conceptual_relationships.id"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categorias.id"), nullable=True
    )
    memo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memos.id"), nullable=True
    )

    content: Mapped[str] = mapped_column(Text)
    ecosystem_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)


# ═══════════════════════════════════════════════════════════════════
# T05 — Layout del ecosistema (persistencia de posiciones)
# ═══════════════════════════════════════════════════════════════════


class EcosystemLayout(Base, TimestampMixin):
    __tablename__ = "ecosystem_layouts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), unique=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)

    blob_positions: Mapped[dict] = mapped_column(JSONB, default=dict)
    ghost_positions: Mapped[dict] = mapped_column(JSONB, default=dict)
    fog_zones: Mapped[dict] = mapped_column(JSONB, default=dict)
    physics_params: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relaciones
    proyecto = relationship("Proyecto", back_populates="ecosystem_layout")
