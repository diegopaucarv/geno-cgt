"""C01_S01_precoding_selective

Revision ID: 010
Revises: 009
Create Date: 2026-06-16

C01: Añade population_assumption (JSONB) a proyectos.
S01: Añade parent_category_id (FK self) a categorias.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "010"
down_revision: Union[str, Sequence[str], None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "proyectos", sa.Column("population_assumption", JSONB(), nullable=True)
    )
    op.add_column(
        "categorias",
        sa.Column(
            "parent_category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categorias.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("categorias", "parent_category_id")
    op.drop_column("proyectos", "population_assumption")
