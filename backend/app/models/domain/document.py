# backend/app/models/domain/document.py
import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Documento(Base, TimestampMixin):
    __tablename__ = "documentos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    original_filename = mapped_column(String(255))
    tipo_de_fuente: Mapped[str] = mapped_column(
        String(50)
    )  # AUDIO_VIDEO, GRUPO_FOCAL, etc.

    # La ruta al archivo físico crudo en MinIO (S3)
    ruta_s3: Mapped[str] = mapped_column(String(1000), nullable=True)
    storage_key = mapped_column(String(500), unique=True)
    mime_type = mapped_column(String(100))
    size_bytes = mapped_column(Integer)
    # Metadatos flexibles (estructuras complejas, resúmenes IA)
    metadatos: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relaciones
    proyecto = relationship("Proyecto", back_populates="documentos")
    segmentos = relationship(
        "Segmento", back_populates="documento", cascade="all, delete-orphan"
    )
