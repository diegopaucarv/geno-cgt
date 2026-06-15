"""C06_prime_mover_on_document_processes

Revision ID: 011
Revises: 010
Create Date: 2026-06-16

Añade columnas prime_mover y prime_mover_confidence a document_processes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, Sequence[str], None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_processes",
        sa.Column("prime_mover", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_processes",
        sa.Column("prime_mover_confidence", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_processes", "prime_mover_confidence")
    op.drop_column("document_processes", "prime_mover")
