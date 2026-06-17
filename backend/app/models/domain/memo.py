# backend/app/models/domain/memo.py
import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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

    # ── F0.3.1: Versionado y campos estructurados ────
    version: Mapped[int] = mapped_column(Integer, default=1)
    """Versión del memo. Se incrementa al editar o al absorber en una categoría."""

    parent_memo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memos.id"), nullable=True
    )
    """Memo padre en una cadena de versionado o derivación. NULL = memo original."""

    structured_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Campos estructurados generados por MemoMaker:
    {sorting_family, cross_references, tables, correlations, tipologias}."""

    user_created: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_at_creation: Mapped[str | None] = mapped_column(String(50), nullable=True)
