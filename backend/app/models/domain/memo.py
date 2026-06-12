# backend/app/models/domain/memo.py
import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Memo(Base, TimestampMixin):
    __tablename__ = "memos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    autor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))

    tipo: Mapped[str] = mapped_column(
        String(50)
    )  # HIPOTESIS, METODOLOGICO, MUESTREO, etc.
    estado: Mapped[str] = mapped_column(String(50), default="ABIERTO")
    contenido: Mapped[str] = mapped_column(Text)
    es_confidencial: Mapped[bool] = mapped_column(Boolean, default=False)
    hash_tema: Mapped[str] = mapped_column(String(256), nullable=True)
