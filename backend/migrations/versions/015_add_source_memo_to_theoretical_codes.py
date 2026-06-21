"""add_source_memo_to_theoretical_codes

Revision ID: 015
Revises: a26195ceb7f0
Create Date: 2026-06-21

Añade source_memo_id a theoretical_codes para soportar sincronización Memo↔Entidad (P4 DeepDive).
Permite que los theoretical_codes creados manualmente desde un memo mantengan la traza
de su memo de origen, igual que categorias.source_memo_id.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, Sequence[str], None] = "a26195ceb7f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "theoretical_codes",
        sa.Column(
            "source_memo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memos.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("theoretical_codes", "source_memo_id")
