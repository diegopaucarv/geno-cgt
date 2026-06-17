# backend/app/models/domain/incident.py
"""
Modelos para extracción, comparación y agrupamiento de incidentes CGT.

F0.1 — Tablas nuevas (CHECKLIST_CGT_REFACTOR.md):
  - extracted_incidents: Incidentes extraídos por segmento (Fase A, incident_extractor FLASH)
  - incident_comparisons: Comparaciones por pares entre incidentes (Fase B, incident_comparator PRO)
  - incident_groups: Grupos de incidentes intercambiables etiquetados (Fase B, pattern_labeler PRO)
"""

from __future__ import annotations

import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class ExtractedIncident(Base, TimestampMixin):
    """Incidente extraído de un segmento por el incident_extractor (FLASH, per-segmento).

    Cada segmento baseline produce un incidente. El incident_extractor aplica
    las 4 preguntas de Glaser (pregunta 4 parametrizada por object_of_study)
    y produce un "jot" (gerundio) + keep_moving flag.
    """

    __tablename__ = "extracted_incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    segmento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("segmentos.id"), index=True
    )
    documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentos.id"), index=True
    )
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), index=True
    )

    # ── Output del incident_extractor ──────────────────
    jot_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Jot en gerundio. Primera impresión del incidente.
    Ej: 'Escaneando el horizonte de amenazas'."""

    keep_moving: Mapped[bool] = mapped_column(Boolean, default=True)
    """¿Hay más patrones en este segmento? False = segmento agotado."""

    tipo_dato_glaser: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """baseline | properline | interpreted | vague.
    Confirmado o corregido por glaser_data_classifier (⚙️+FLASH)."""

    preguntas_glaser_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    """Respuestas estructuradas a las 4 preguntas de Glaser:
    {
      what_is_this_about: str,
      what_category: str,
      what_is_happening: str,
      participants_pattern: str (pregunta 4, parametrizada por object_of_study),
      confidence: float (0.0-1.0)
    }"""

    patrón_documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_processes.id"), nullable=True
    )
    """FK al DocumentProcess. Vincula este incidente con el patrón individual
    del entrevistado (core_pattern_extractor, PRO, per-documento)."""


class IncidentComparison(Base, TimestampMixin):
    """Comparación por pares entre dos incidentes (incident_comparator, PRO, Fase B1).

    El comparator recibe SOLO incidentes (sin ver categorías existentes) y
    evalúa intercambiabilidad entre pares. Resultados se usan para agrupar
    incidentes en incident_groups.

    Estrategia incremental (resolución C6): primera ejecución compara todos
    contra todos. Subsecuentes solo comparan incidentes nuevos contra grupos
    existentes y entre sí.
    """

    __tablename__ = "incident_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_incidents.id")
    )
    incident_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_incidents.id")
    )
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), index=True
    )

    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)
    """Score de similitud semántica (0.0-1.0). Pre-filtro por embedding
    antes de la comparación LLM."""

    are_interchangeable: Mapped[bool] = mapped_column(Boolean, default=False)
    """¿Son intercambiables? True = miden el mismo fenómeno subyacente."""

    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Justificación de la decisión de intercambiabilidad."""


class IncidentGroup(Base, TimestampMixin):
    """Grupo de incidentes intercambiables etiquetado por el pattern_labeler (PRO, Fase B2).

    Tras la comparación de pares (B1), los incidentes intercambiables se agrupan.
    El pattern_labeler propone etiquetas para cada grupo. El label_critic (FLASH, B3)
    las evalúa en un bucle SelfRefinement de máx 3 iteraciones.
    """

    __tablename__ = "incident_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), index=True
    )

    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """Etiqueta propuesta por el pattern_labeler. Gerundio.
    NULL mientras el grupo no ha sido etiquetado."""

    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Definición de la categoría propuesta por el pattern_labeler."""

    status: Mapped[str] = mapped_column(String(50), default="open")
    """open | labeled | approved | rejected"""

    incident_ids_json: Mapped[list] = mapped_column(JSONB, default=list)
    """UUIDs de los incidentes en este grupo.
    ⚠️ DÉBIL — JSONB sin FK. La trazabilidad fuerte está en incident_comparisons."""

    labeled_by_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    """Nombre del agente que realizó la etiquetación (pattern_labeler)."""

    critic_verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Veredicto del label_critic (B3):
    {verdict: SAT|MOD|FORCED, issues: [{type, description}], all_valid: bool}"""
