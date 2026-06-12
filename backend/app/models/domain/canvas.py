import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class LienzoDelPlanDeAnalisis(Base, TimestampMixin):
    __tablename__ = "lienzos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id"), unique=True
    )

    version_lienzo: Mapped[int] = mapped_column(Integer, default=1)
    esta_bloqueado: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relaciones
    proyecto = relationship("Proyecto", back_populates="lienzo")
    nodos = relationship(
        "NodoDeLienzo", back_populates="lienzo", cascade="all, delete-orphan"
    )
    bordes = relationship(
        "BordeDeLienzo", back_populates="lienzo", cascade="all, delete-orphan"
    )


class NodoDeLienzo(Base, TimestampMixin):
    __tablename__ = "nodos_lienzo"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lienzo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lienzos.id"))

    tipo: Mapped[str] = mapped_column(
        String(50)
    )  # FUENTE_DE_DATOS, FASE, PUERTA_DE_DECISION
    etiqueta: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(50), default="NO_INICIADO")

    pos_x: Mapped[float] = mapped_column(Float, default=0.0)
    pos_y: Mapped[float] = mapped_column(Float, default=0.0)

    parametros_configuracion: Mapped[dict] = mapped_column(JSONB, default=dict)
    es_obligatorio: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    lienzo = relationship("LienzoDelPlanDeAnalisis", back_populates="nodos")


class BordeDeLienzo(Base, TimestampMixin):
    __tablename__ = "bordes_lienzo"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lienzo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lienzos.id"))

    nodo_origen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodos_lienzo.id"))
    nodo_destino_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodos_lienzo.id"))

    tipo_de_dato: Mapped[str] = mapped_column(String(100), nullable=True)
    es_condicional: Mapped[bool] = mapped_column(Boolean, default=False)
    expresion_condicional: Mapped[str] = mapped_column(String(500), nullable=True)

    # Relaciones
    lienzo = relationship("LienzoDelPlanDeAnalisis", back_populates="bordes")
    nodo_origen = relationship("NodoDeLienzo", foreign_keys=[nodo_origen_id])
    nodo_destino = relationship("NodoDeLienzo", foreign_keys=[nodo_destino_id])
