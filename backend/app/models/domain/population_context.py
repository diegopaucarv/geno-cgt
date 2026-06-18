# backend/app/models/domain/population_context.py
"""
Memoria acumulativa de largo plazo sobre la población de estudio.

Agente A1 (POPULATION_CONTEXT_BUILDER) expande este registro
iterativamente con cada nuevo documento procesado.
"""

from __future__ import annotations

import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class PopulationContext(Base, TimestampMixin):
    __tablename__ = "population_contexts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    # ── Dimensiones del contexto ──────────────────────
    surprising_details: Mapped[str] = mapped_column(Text, default="")
    """Detalles sorprendentes o diferenciales sobre esta población
    que no anticipábamos. Lo que los datos revelan que contradice
    o expande nuestras expectativas."""

    language_patterns: Mapped[str] = mapped_column(Text, default="")
    """Patrones de lenguaje: metáforas recurrentes, eufemismos,
    estructuras discursivas, términos nativos, jerga del grupo."""

    data_production_context: Mapped[str] = mapped_column(Text, default="")
    """Contexto de producción de los datos: condiciones de los documentos,
    señales de deseabilidad social, fatiga, evasión, apertura,
    dinámicas de poder autor-participante."""

    # ── Trazabilidad ──────────────────────────────────
    source_document_ids: Mapped[list] = mapped_column(JSONB, default=list)
    """UUIDs de los documentos que han contribuido a esta versión
    del contexto poblacional."""

    version: Mapped[int] = mapped_column(Integer, default=1)
    """Versión del contexto. Se incrementa con cada actualización."""
