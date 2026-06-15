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


# Importar aquí para que SQLAlchemy registre la clase antes de resolver relaciones
from app.models.domain.canvas import LienzoDelPlanDeAnalisis  # noqa: E402,F401
