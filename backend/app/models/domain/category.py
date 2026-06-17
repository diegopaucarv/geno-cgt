# backend/app/models/domain/category.py
import uuid

from app.models.base import Base, TimestampMixin
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Categoria(Base, TimestampMixin):
    __tablename__ = "categorias"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    nombre: Mapped[str] = mapped_column(String(200))
    definicion: Mapped[str] = mapped_column(Text)
    limites: Mapped[str] = mapped_column(Text, nullable=True)

    estado_saturacion: Mapped[str] = mapped_column(String(50), default="ABIERTO")
    puntaje_relevancia: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    es_central: Mapped[bool] = mapped_column(Boolean, default=False)

    # Vector para calcular la saturación de forma matemática (entropía de embeddings)
    embedding_centroide: Mapped[list[float]] = mapped_column(
        Vector(1024), nullable=True
    )

    # ── A6: TheoSampler ─────────────────────────────
    saturation_docs: Mapped[list] = mapped_column(JSONB, default=list)
    """UUIDs de documentos ya saturados. Alimenta el ANTI-JOIN del TheoSampler."""

    # ── S01: Jerarquía de categorías ────────────────
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categorias.id"), nullable=True
    )
    """Categoría padre. NULL = categoría raíz."""

    source_memo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memos.id"), nullable=True
    )
    """Memo de origen. NOT NULL = creada manualmente. NULL = generada por agente."""

    # ── F0.3.2: Panel de 4 señales de saturación ────
    saturation_panel_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Cache pre-calculada de las 4 señales de saturación:
    {matematica: {rolling_std, status},
     cualitativa: {paradigm_window, did_expand_last_5},
     cobertura: {propiedades_cubiertas, total_propiedades},
     integracion: {relaciones_documentadas, categorias_vinculadas}}.
    Actualizado por task_core_saturation_loop (F4.2)."""

    # ── F0.3.3: Etiqueta en gerundio ────────────────
    gerundio_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """Etiqueta en gerundio propuesta por el pattern_labeler (B2).
    Ej: 'Negociando permanencia', 'Escaneando amenazas'.
    NULL hasta que el labeler procesa el grupo de incidentes."""

    # Relaciones
    doc_codes = relationship(
        "DocCode", back_populates="categoria", cascade="all, delete-orphan"
    )
    codigos_segmento = relationship(
        "CodigoSegmento", back_populates="categoria", cascade="all, delete-orphan"
    )
    parent = relationship(
        "Categoria", remote_side="[Categoria.id]", back_populates="children"
    )
    children = relationship(
        "Categoria", back_populates="parent", cascade="all, delete-orphan"
    )
    definition_versions = relationship(
        "CategoryDefinitionVersion",
        back_populates="category",
        cascade="all, delete-orphan",
    )
    paradigm_states = relationship(
        "ParadigmState", back_populates="category", cascade="all, delete-orphan"
    )


# Importar aquí para resolver referencias circulares
from app.models.domain.synthesis import ParadigmState  # noqa: E402,F401
from app.models.domain.theory import CategoryDefinitionVersion  # noqa: E402,F401


class DocCode(Base, TimestampMixin):
    """Tabla pivote enriquecida que vincula Documentos con Categorías."""

    __tablename__ = "doc_codes"

    documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentos.id"), primary_key=True
    )
    categoria_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), primary_key=True
    )

    estado: Mapped[str] = mapped_column(
        String(50), default="presente"
    )  # 'presente', 'ausente', 'no_evaluado'
    resumen_evidencia: Mapped[str] = mapped_column(
        Text
    )  # Síntesis de por qué se asignó este código

    # Relaciones
    categoria = relationship("Categoria", back_populates="doc_codes")


class CodigoSegmento(Base, TimestampMixin):
    """Tabla pivote que vincula Segmentos con Categorías (codificación a nivel segmento)."""

    __tablename__ = "codigos_segmento"

    segmento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("segmentos.id"), primary_key=True
    )
    categoria_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), primary_key=True
    )

    estado: Mapped[str] = mapped_column(
        String(50), default="asignado"
    )  # 'asignado', 'confirmado', 'descartado'
    confianza: Mapped[float] = mapped_column(
        Float, default=1.0
    )  # 0.0 - 1.0 (útil para recomendaciones automáticas)
    origen: Mapped[str] = mapped_column(
        String(50), default="manual"
    )  # 'manual', 'ia', 'recomendacion'

    # Relaciones
    segmento = relationship("Segmento", back_populates="codigos")
    categoria = relationship("Categoria", back_populates="codigos_segmento")
