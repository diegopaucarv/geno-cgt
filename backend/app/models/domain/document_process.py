# backend/app/models/domain/document_process.py
"""
Proceso central que cada documento/entrevistado intenta resolver.

Agente A2 (PROCESS_IDENTIFIER) identifica este proceso para cada
documento y lo compara con el documento anterior.
"""

from __future__ import annotations

import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class DocumentProcess(Base, TimestampMixin):
    __tablename__ = "document_processes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id"))
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    # ── Proceso identificado ──────────────────────────
    process_description: Mapped[str] = mapped_column(Text)
    """Descripción en gerundio del proceso central que este entrevistado
    intenta resolver continuamente. Ej: 'Negociando permanencia en la
    plataforma', 'Balanceando riesgo y visibilidad'."""

    # ── Comparación con el documento anterior ─────────
    similarity_to_previous: Mapped[str] = mapped_column(Text, nullable=True)
    """En qué se PARECE el proceso de este documento al del anterior.
    NULL para el primer documento del proyecto."""

    difference_from_previous: Mapped[str] = mapped_column(Text, nullable=True)
    """En qué se DIFERENCIA el proceso de este documento del anterior.
    NULL para el primer documento del proyecto."""

    previous_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentos.id"), nullable=True
    )
    """Documento anterior en la secuencia de procesamiento."""
