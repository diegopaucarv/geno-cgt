# backend/app/models/domain/user.py
import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Usuario(Base, TimestampMixin):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(100))
    correo: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    rol: Mapped[str] = mapped_column(String(50), default="INVESTIGADOR_PRINCIPAL")
    plan: Mapped[str] = mapped_column(String(50), default="BASICO")
    tokens_mensuales_usados: Mapped[int] = mapped_column(default=0)

    # Relación bidireccional con proyectos
    proyectos = relationship("Proyecto", back_populates="creador")
