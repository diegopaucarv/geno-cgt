"""supuesto_poblacional_on_proyectos

Revision ID: 007
Revises: 006
Create Date: 2026-06-15

Añade columna supuesto_poblacional a proyectos.
Permite al investigador definir qué intenta resolver continuamente la población.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "proyectos",
        sa.Column("supuesto_poblacional", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proyectos", "supuesto_poblacional")
