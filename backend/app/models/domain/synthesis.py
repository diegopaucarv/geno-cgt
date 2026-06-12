# backend/app/models/domain/synthesis.py
import uuid

from app.models.base import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
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
