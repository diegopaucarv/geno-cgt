"""ProjectConfigHistory — registro inmutable de cambios en la configuración del proyecto.

Cada vez que un agente o el usuario modifica un campo de configuración del proyecto
(population_assumption, object_of_study, coding_styles, config_segmentacion, etc.),
se inserta una fila en esta tabla. Funciona como un "git log" de la configuración.
"""

from __future__ import annotations

import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ProjectConfigHistory(Base, TimestampMixin):
    """Registro inmutable de un cambio de configuración en un proyecto."""

    __tablename__ = "project_config_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    # ── Qué cambió ──
    field: Mapped[str] = mapped_column(String(100))
    """Campo modificado. Ej: 'population_assumption.temporal_frame',
    'object_of_study', 'coding_styles', 'config_segmentacion'."""

    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Valor anterior (serializado como string/JSON). NULL si es creación."""

    new_value: Mapped[str] = mapped_column(Text)
    """Valor nuevo (serializado como string/JSON)."""

    # ── Quién / qué lo hizo ──
    triggered_by: Mapped[str] = mapped_column(String(50), default="user")
    """Quién disparó el cambio:
    - 'user' — el investigador manualmente
    - nombre del agente (ej: 'population_generalizer', 'core_pattern_verifier')
    - 'system' — inicialización automática
    """

    agent_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    """ID del pipeline_run o tarea que generó este cambio (si fue un agente)."""

    # ── Metadato de la mutación ──
    mutation_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """Nivel de policy que se aplicó:
    'auto' | 'suggest' | 'require_approval' | 'locked'
    NULL si fue cambio manual del usuario."""

    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Justificación del cambio (provista por el agente o el usuario)."""

    confidence: Mapped[float | None] = mapped_column(nullable=True)
    """Confianza del agente en el cambio propuesto (0.0 a 1.0). NULL si manual."""

    # ── Datos extra ──
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Contexto adicional (ej: documentos que motivaron el cambio, diff completo)."""

    # Relación inversa
    proyecto = relationship("Proyecto", back_populates="config_history")
