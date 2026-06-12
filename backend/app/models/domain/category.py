# backend/app/models/domain/category.py
import uuid

from app.models.base import Base, TimestampMixin
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Categoria(Base, TimestampMixin):
    __tablename__ = "categorias"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    nombre: Mapped[str] = mapped_column(String(200))
    definicion: Mapped[str] = mapped_column(Text)
    limites: Mapped[str] = mapped_column(Text, nullable=True)

    estado_saturacion: Mapped[str] = mapped_column(String(50), default="ABIERTO")
    puntaje_relevancia: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    es_central: Mapped[bool] = mapped_column(Boolean, default=False)

    # Vector para calcular la saturación de forma matemática (entropía de embeddings)
    embedding_centroide: Mapped[list[float]] = mapped_column(
        Vector(1536), nullable=True
    )

    # Relaciones
    doc_codes = relationship(
        "DocCode", back_populates="categoria", cascade="all, delete-orphan"
    )


class DocCode(Base, TimestampMixin):
    """Tabla pivote enriquecida que vincula Documentos con Categorías."""

    __tablename__ = "doc_codes"

    documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentos.id"), primary_key=True
    )
    categoria_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id"), primary_key=True
    )

    estado: Mapped[str] = mapped_column(
        String(50), default="presente"
    )  # 'presente', 'ausente', 'no_evaluado'
    resumen_evidencia: Mapped[str] = mapped_column(
        Text
    )  # Síntesis de por qué se asignó este código

    # Relaciones
    categoria = relationship("Categoria", back_populates="doc_codes")
