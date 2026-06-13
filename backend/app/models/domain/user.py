# backend/app/models/domain/user.py
import uuid

from app.models.base import Base, TimestampMixin
from app.models.domain.enums import RolDeUsuario, TipoPlanSuscripcion
from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Usuario(Base, TimestampMixin):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(100))
    correo: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    rol: Mapped[RolDeUsuario] = mapped_column(
        Enum(RolDeUsuario, name="rol_usuario_enum"),
        default=RolDeUsuario.INVESTIGADOR_PRINCIPAL,
    )
    plan: Mapped[TipoPlanSuscripcion] = mapped_column(
        Enum(TipoPlanSuscripcion, name="plan_suscripcion_enum"),
        default=TipoPlanSuscripcion.BASICO,
    )
    tokens_mensuales_usados: Mapped[int] = mapped_column(default=0)

    # Relación bidireccional con proyectos
    proyectos = relationship("Proyecto", back_populates="creador")
