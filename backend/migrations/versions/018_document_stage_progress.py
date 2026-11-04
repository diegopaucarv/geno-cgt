"""document_stage_progress: tracking de etapas por documento y agente

Revision ID: 018
Revises: 017
Create Date: 2026-11-03

Crea `document_stage_progress`, referenciada por el backend
(`/api/v1/projects/{id}/stage-progress` y los resets de documento) y por los
tres workers (segmentacion NLP, punctuator FAST y clasificador Glaser HEAVY).
Ninguna migracion previa la creaba, asi que cada INSERT fallaba con
`UndefinedTable` y el tracking de progreso se perdia.

La PK compuesta (documento_id, agent_id) es la que hace idempotentes los
`INSERT ... ON CONFLICT DO NOTHING` sin target explicito.

Es idempotente: si la tabla ya existe (p. ej. creada a mano para desbloquear
un entorno), el upgrade retorna sin hacer nada y Alembic sella la revision.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: Union[str, Sequence[str], None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "document_stage_progress" in _tables():
        return

    op.create_table(
        "document_stage_progress",
        sa.Column("documento_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"],
            ["documentos.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("documento_id", "agent_id"),
    )


def downgrade() -> None:
    if "document_stage_progress" in _tables():
        op.drop_table("document_stage_progress")
