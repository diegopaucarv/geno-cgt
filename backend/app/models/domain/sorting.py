# backend/app/models/domain/sorting.py
"""
Modelos para Sorting Log y MemoMaker (Theoretical Playground — Fase 6b).

F0.2 — Tablas nuevas (CHECKLIST_CGT_REFACTOR.md):
  - memo_sorting_attempts: Intentos de ordenamiento teórico de memos
  - memo_sorting_groups: Grupos de memos formados durante el sorting
"""

from __future__ import annotations

import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class MemoSortingAttempt(Base, TimestampMixin):
    """Intento de ordenamiento teórico de memos contra una familia de códigos teóricos.

    Cada vez que el investigador arrastra memos hacia una familia teórica
    en el Playground, se crea un attempt. El sistema registra qué memos
    fueron agrupados, cuáles quedaron huérfanos, y cuáles fueron forzados.

    Referencias:
      - kb.md §8 L357-365 (Sorting Log)
      - 3-memomaker.md §4.2 (nueva tabla memo_sorting_attempts)
    """

    __tablename__ = "memo_sorting_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), index=True
    )
    theoretical_code_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("theoretical_codes.id"), nullable=True, index=True
    )
    """Familia de códigos teóricos contra la que se ordena.
    NULL si el sorting es exploratorio (sin familia asignada aún)."""

    # ── Resultados del sorting ────────────────────────
    groups_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    """Grupos formados: {group_label: [memo_id, ...]}.
    Cada grupo representa una afinidad temática dentro de la familia."""

    homeless_json: Mapped[list] = mapped_column(JSONB, default=list)
    """UUIDs de memos que no encajan en ningún grupo.
    Pueden ser absorbidos por ghost_blob_mapper o archivados."""

    forced_json: Mapped[list] = mapped_column(JSONB, default=list)
    """UUIDs de memos forzados en grupos contra recomendación del sistema.
    Marcados para revisión en el próximo intento."""

    thin_json: Mapped[list] = mapped_column(JSONB, default=list)
    """UUIDs de grupos débiles (1 solo memo, sin evidencia suficiente).
    Señal para el investigador de que necesita más datos."""

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Puntaje de calidad del sorting (0.0-1.0).
    Calculado por cross_family_synthesizer: cobertura, cohesión, discriminación."""


class MemoSortingGroup(Base, TimestampMixin):
    """Grupo individual de memos dentro de un sorting attempt.

    Cada grupo contiene memos que el investigador (o el memo_theoretical_tagger)
    considera afines. El sistema registra afinidad cruzada con otras familias
    para detectar conexiones inter-familia.

    Referencias:
      - kb.md §8 L357-365 (Sorting Log)
      - 3-memomaker.md §4.2 (cross-family affinity)
    """

    __tablename__ = "memo_sorting_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memo_sorting_attempts.id"), index=True
    )
    """Attempt padre. Un intento puede tener múltiples grupos."""

    memos_json: Mapped[list] = mapped_column(JSONB, default=list)
    """UUIDs de los memos en este grupo.
    ⚠️ DÉBIL — JSONB sin FK. La FK fuerte está en attempt_id → memo_sorting_attempts."""

    cross_family_affinity_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    """Afinidad cruzada con otras familias teóricas:
    {family_name: score (0.0-1.0), ...}.
    Detectada por memo_theoretical_tagger (FLASH) durante pre-clasificación."""
