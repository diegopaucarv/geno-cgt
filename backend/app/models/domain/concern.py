# backend/app/models/domain/concern.py
import uuid
from datetime import datetime

from app.models.base import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Concern(Base):
    """Gerund concern identified by the A14 concern labeler during coding.

    Concerns represent recurring patterns of participant behavior expressed
    as gerunds (e.g. "Negotiating permanence", "Scanning threats"). They
    bridge the gap between low-level incidents and high-level categories.
    """

    __tablename__ = "concerns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE")
    )

    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="candidate")
    # candidate | confirmed | rejected

    identified_at_batch: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relaciones
    proyecto = relationship("Proyecto", back_populates="concerns")


# Importar aquí para resolver referencias circulares
from app.models.domain.project import Proyecto  # noqa: E402,F401
