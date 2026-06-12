# backend/app/models/exec_log.py
import uuid

from app.models.base import Base, TimestampMixin
from sqlalchemy import Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class RegistroEjecucionAgente(Base, TimestampMixin):
    """Log inmutable y estructurado para trazabilidad de IA."""

    __tablename__ = "ejecuciones_agentes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agente_id: Mapped[str] = mapped_column(String(100))  # Ej: "AgenteCritico"
    fase_id: Mapped[str] = mapped_column(String(100), nullable=True)

    modelo_llm: Mapped[str] = mapped_column(String(100))
    hash_entrada: Mapped[str] = mapped_column(String(256))

    # Aquí guardamos TODO: el prompt, la respuesta cruda, el JSON parseado y el veredicto
    payload_completo: Mapped[dict] = mapped_column(JSONB, default=dict)

    costo_usd: Mapped[float] = mapped_column(Float, default=0.0)
