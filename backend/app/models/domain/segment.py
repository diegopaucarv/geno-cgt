# backend/app/models/domain/segment.py
import uuid

from app.models.base import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Segmento(Base):
    __tablename__ = "segmentos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id"))

    texto: Mapped[str] = mapped_column(Text)
    parafrasis: Mapped[str] = mapped_column(Text, nullable=True)
    posicion: Mapped[int] = mapped_column(Integer)  # Orden en el documento original
    conteo_tokens: Mapped[int] = mapped_column(Integer, default=0)

    es_anomalia: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Clasificación Glaser ────────────────────────
    tipo_dato_glaser: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """
    baseline_data | properline_data | interpreted_data | vague_data | interviewer_context.
    Clasificado por IA en batch (classify_segments_batch).
    interviewer_context = pregunta del autor, título, o metadata.
    """

    # ── Reconstrucción determinista (A2 — Hacedor de texto) ──
    first_10: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """Primeras 10 palabras exactas. Ancla textual para reconstrucción determinista."""
    start_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Posición de inicio en el texto original (0-based char index)."""
    end_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Posición de fin en el texto original (0-based char index)."""
    is_exact_match: Mapped[bool] = mapped_column(Boolean, default=True)
    """False si el ancla no se encontró en el original (fallback a fuzzy match)."""

    # Vector de 1024 dimensiones para búsqueda semántica (TEI — voyage-4-nano)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    # Relaciones
    documento = relationship("Documento", back_populates="segmentos")
    codigos = relationship(
        "CodigoSegmento", back_populates="segmento", cascade="all, delete-orphan"
    )
