# backend/app/models/langgraph_checkpoints.py
from app.models.base import Base
from sqlalchemy import LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class LangGraphCheckpoint(Base):
    """Tabla diseñada para conectar con el PostgresSaver de LangGraph."""

    __tablename__ = "langgraph_checkpoints"

    # LangGraph usa composite primary keys (thread_id + checkpoint_id)
    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    parent_checkpoint_id: Mapped[str] = mapped_column(String(255), nullable=True)

    # El estado completo del grafo en ese instante temporal
    checkpoint: Mapped[dict] = mapped_column(JSONB)

    # Metadatos del framework
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
