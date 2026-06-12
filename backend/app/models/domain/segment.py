# backend/app/models/domain/segment.py
import uuid

from app.models.base import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Segmento(Base):
    __tablename__ = "segmentos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id"))

    texto: Mapped[str] = mapped_column(Text)
    parafrasis: Mapped[str] = mapped_column(Text, nullable=True)
    posicion: Mapped[int] = mapped_column(Integer)  # Orden en el documento original
    conteo_tokens: Mapped[int] = mapped_column(Integer, default=0)

    es_anomalia: Mapped[bool] = mapped_column(Boolean, default=False)

    # ¡La magia de pgvector! Vector de 1536 dimensiones (estándar de OpenAI/BGE)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=True)

    # Relaciones
    documento = relationship("Documento", back_populates="segmentos")
