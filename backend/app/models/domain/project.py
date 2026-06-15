# backend/app/models/domain/project.py
import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

DEFAULT_POPULATION_ASSUMPTION = (
    "hábitos hipotéticos de comportamiento que procesan "
    "preocupaciones similares o más amplias en la vida diaria "
    "del entrevistado"
)


class Proyecto(Base, TimestampMixin):
    __tablename__ = "proyectos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(200))
    ruta_de_codificacion: Mapped[str] = mapped_column(
        String(50), default="ABDUCTIVA_CGT"
    )
    estado: Mapped[str] = mapped_column(String(50), default="ACTIVO")

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


# Importar aquí para que SQLAlchemy registre la clase antes de resolver relaciones
from app.models.domain.canvas import LienzoDelPlanDeAnalisis  # noqa: E402,F401
from app.models.domain.theory import EcosystemLayout  # noqa: E402,F401
