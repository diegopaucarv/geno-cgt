# backend/app/models/domain/project.py
import uuid

from app.core.config import DEFAULT_POPULATION_ASSUMPTION
from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Proyecto(Base, TimestampMixin):
    __tablename__ = "proyectos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(200))
    ruta_de_codificacion: Mapped[str] = mapped_column(
        String(50), default="ABDUCTIVA_CGT"
    )
    estado: Mapped[str] = mapped_column(String(50), default="collecting")
    # "collecting" | "coding" | "finding_cc" | "reducing" |
    # "saturating" | "building_db" | "playground_ready" | "completed"

    # Supuesto poblacional configurable por el investigador.
    # Qué intenta resolver continuamente esta población.
    # Ej: "procesos sociocognitivos de adaptación a plataformas digitales"
    supuesto_poblacional: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=DEFAULT_POPULATION_ASSUMPTION
    )

    # ── Configuración de segmentación por proyecto ───
    config_segmentacion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """
    Configuración del ProgressiveSegmenter:
    - window_size: int (default 3)
    - similarity_threshold: float (default 0.75)
    - max_tokens: int (default 1024)
    - reinert_micro: bool (default true)
    """

    # C01: Population assumption structurado
    population_assumption: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """
    Configuracion epistemologica del proyecto:
    - object_of_study: "concern" | "emotion" | "behavior" | "discourse" | "identity" | "custom"
    - temporal_frame: "present_continuous" | "retrospective" | "prospective" | "longitudinal"
    - spatial_frame: "cohabiting_group" | "sparse" | "high_diversity"
    - population_description: str
    - gerundio_esperado: str (opcional, emerge después de A14)
    - custom_label: str (solo si object_of_study="custom")
    - coding_styles: list[str] (default ["gerundio", "in_vivo"]) — estilo de codificación (Saldaña)
    """

    # ── F0.3.4: Instrucción de estilo de codificación ──
    coding_style_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Instrucción compilada de coding_styles inyectada en prompts de agentes.
    Derivada de population_assumption.coding_styles y compilada por
    coding_styles.py al guardar la configuración del proyecto."""

    # ── F0.3.5: Objeto de estudio como columna dedicada ──
    object_of_study: Mapped[str] = mapped_column(String(50), default="concern")
    """Tipo de patrón humano que se busca. Extraído de population_assumption
    a columna dedicada para acceso rápido en agentes.
    concern | emotion | behavior | discourse | identity | custom"""

    # ── F0.3.6: Idioma del usuario para outputs del LLM ──
    language: Mapped[str] = mapped_column(String(5), default="es")
    """Idioma para outputs del LLM. Matching frontend i18n.
    es | en | de | pt. Default: es (Spanish)."""

    # ── Política de mutaciones automáticas ──
    config_mutation_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Controla qué campos de configuración puede modificar el sistema
    automáticamente y cuáles requieren aprobación del investigador.

    Claves posibles y sus niveles:
    - population_description: "auto" | "suggest" | "require_approval" | "locked"
    - temporal_frame: "auto" | "suggest" | "require_approval" | "locked"
    - spatial_frame: "auto" | "suggest" | "require_approval" | "locked"
    - object_of_study: "auto" | "suggest" | "require_approval" | "locked"
    - pattern_of_interest: "auto" | "suggest" | "require_approval" | "locked"
    - coding_styles: "auto" | "suggest" | "require_approval" | "locked"
    - gerundio_esperado: "auto" | "suggest" | "require_approval" | "locked"
    - segmentation_config: "auto" | "suggest" | "require_approval" | "locked"

    Valores por defecto para proyecto nuevo:
    {
        "population_description": "suggest",
        "temporal_frame": "suggest",
        "spatial_frame": "suggest",
        "object_of_study": "require_approval",
        "pattern_of_interest": "require_approval",
        "coding_styles": "suggest",
        "gerundio_esperado": "suggest",
        "segmentation_config": "auto"
    }
    """

    creador_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))

    # Relaciones
    creador = relationship("Usuario", back_populates="proyectos")
    documentos = relationship(
        "Documento", back_populates="proyecto", cascade="all, delete-orphan"
    )

    lienzo = relationship(
        "LienzoDelPlanDeAnalisis",
        back_populates="proyecto",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ecosystem_layout = relationship(
        "EcosystemLayout",
        back_populates="proyecto",
        uselist=False,
        cascade="all, delete-orphan",
    )

    config_history = relationship(
        "ProjectConfigHistory",
        back_populates="proyecto",
        cascade="all, delete-orphan",
    )

    concerns = relationship(
        "Concern", back_populates="proyecto", cascade="all, delete-orphan"
    )


# Importar aquí para que SQLAlchemy registre la clase antes de resolver relaciones
from app.models.domain.canvas import LienzoDelPlanDeAnalisis  # noqa: E402,F401
from app.models.domain.concern import Concern  # noqa: E402,F401
from app.models.domain.project_config_history import (
    ProjectConfigHistory,  # noqa: E402,F401
)
from app.models.domain.theory import EcosystemLayout  # noqa: E402,F401
