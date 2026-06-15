# backend/app/models/domain/project.py
import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Proyecto(Base, TimestampMixin):
    __tablename__ = "proyectos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(200))
    ruta_de_codificacion: Mapped[str] = mapped_column(
        String(50), default="ABDUCTIVA_CGT"
    )
    estado: Mapped[str] = mapped_column(String(50), default="ACTIVO")

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
