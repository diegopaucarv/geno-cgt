"""add_batch_and_hitl_columns_to_proyectos

Revision ID: a26195ceb7f0
Revises: eba2e69cb207
Create Date: 2026-06-20 18:02:23.722623

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a26195ceb7f0"
down_revision: Union[str, Sequence[str], None] = "eba2e69cb207"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "proyectos",
        sa.Column(
            "batch_number", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column("proyectos", sa.Column("chosen_concern", sa.Text(), nullable=True))
    op.add_column("proyectos", sa.Column("chosen_population", sa.Text(), nullable=True))
    op.add_column(
        "proyectos",
        sa.Column(
            "pause_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("proyectos", "pause_mode")
    op.drop_column("proyectos", "chosen_population")
    op.drop_column("proyectos", "chosen_concern")
    op.drop_column("proyectos", "batch_number")
