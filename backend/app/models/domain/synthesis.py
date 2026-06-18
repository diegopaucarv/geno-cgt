# backend/app/models/domain/synthesis.py
import uuid

from app.models.base import Base, TimestampMixin
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class CodePrototype(Base):
    __tablename__ = "code_prototypes"

    code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), primary_key=True
    )
    segment_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list
    )  # Hasta 3 segmentos ejemplares
    updated_at: Mapped[str] = mapped_column(String(100), nullable=True)


class CodeDocumentSummary(Base):
    """Síntesis cualitativa intra-documento."""

    __tablename__ = "code_document_summaries"

    code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentos.id"), primary_key=True
    )

    summary: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(100), nullable=True)


class CodeGlobalSummary(Base):
    """Síntesis consolidada inter-documento de una categoría."""

    __tablename__ = "code_global_summaries"

    code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), primary_key=True
    )
    summary: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class SaturationMetrics(Base):
    """Métricas continuas calculadas por el IncrementalSaturationCalculator."""

    __tablename__ = "saturation_metrics"

    code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), primary_key=True
    )
    centroid: Mapped[list[float]] = mapped_column(
        Vector(1024)
    )  # Embedding promedio de resúmenes recientes
    rolling_std: Mapped[float] = mapped_column(Float, default=0.0)
    saturation_status: Mapped[str] = mapped_column(String(50), default="unsaturated")
    documents_since_change: Mapped[int] = mapped_column(Integer, default=0)


class Hypothesis(Base):
    """Estructura de árbol de pensamientos para hipótesis emergentes."""

    __tablename__ = "hypotheses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), nullable=True
    )

    text: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(50))  # 'general', 'specific', 'emergent'
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="candidate")

    # Auto-referencia para habilitar estructuras jerárquicas de razonamiento (Tree of Thoughts)
    parent_hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hypotheses.id"), nullable=True
    )

    # ── CGT concern labels ──────────────────────────
    concern_labels: Mapped[list] = mapped_column(JSONB, default=list)
    """List of concern labels this hypothesis relates to.
    Example: ['Negotiating permanence', 'Scanning threats'].
    Empty list means unlinked or not yet labeled."""

    batch_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Which batch (1, 2, 3...) produced this hypothesis.
    NULL until the concern labeler batch is assigned."""


class ProcessingState(Base):
    """Rastreador de estado para el procesamiento por lotes e idempotencia."""

    __tablename__ = "processing_states"

    entity_type: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # 'document', 'segment', 'code'
    entity_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    step: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # 'segmented', 'coded', 'synthesized'


class GraphEntity(Base):
    __tablename__ = "graph_entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(100))  # 'person', 'concept', 'event'
    frequency: Mapped[int] = mapped_column(Integer, default=1)


class GraphRelation(Base):
    __tablename__ = "graph_relations"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_entities.id"), primary_key=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_entities.id"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(100), primary_key=True)
    strength: Mapped[float] = mapped_column(Float, default=1.0)


# ═══════════════════════════════════════════════════════════════════════
# A1 — ParadigmState (category saturator.json)
# ═══════════════════════════════════════════════════════════════════════


class ParadigmState(Base, TimestampMixin):
    """
    Estado paradigmático de una categoria. Mantenido por el Integrador
    Paradigmatico (AI Agent1 del category saturator.json).

    Cada iteracion produce una senal booleana did_state_expand.
    La saturación se verifica con ventana deslizante SQL (bool_and).
    """

    __tablename__ = "paradigm_states"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categorias.id"))
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    iteration: Mapped[int] = mapped_column(Integer)
    did_state_expand: Mapped[bool] = mapped_column(Boolean, default=False)
    expansion_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """NEW_DIMENSION | NEW_CONDITION | NEW_CONSEQUENCE | NEW_STRATEGY | NONE"""
    paradigm_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    """{dimensions: [{label, description, incident_ids}], conditions: [...], consequences: [...], strategies: [...]}"""
    integration_memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """Subgrupo de muestreo (como el antiguo agrupa por metadata_group)."""

    # Relaciones
    category = relationship("Categoria", back_populates="paradigm_states")
