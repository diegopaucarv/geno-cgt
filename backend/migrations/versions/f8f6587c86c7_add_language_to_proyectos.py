"""add_language_to_proyectos

Revision ID: f8f6587c86c7
Revises: 013
Create Date: 2026-06-17 10:05:28.741625

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8f6587c86c7"
down_revision: Union[str, Sequence[str], None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """T0 Translation Pattern: agregar language a proyectos."""
    op.add_column(
        "proyectos",
        sa.Column(
            "language",
            sa.String(length=5),
            nullable=False,
            server_default=sa.text("'es'::character varying"),
        ),
    )


def downgrade() -> None:
    op.drop_column("proyectos", "language")
