import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Fase(Base, TimestampMixin):
    __tablename__ = "fases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    # Vinculamos la fase real con la caja visual en el lienzo
    nodo_lienzo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("nodos_lienzo.id"), nullable=True
    )

    numero: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(50), default="PENDIENTE")

    # Relaciones
    proyecto = relationship("Proyecto")
