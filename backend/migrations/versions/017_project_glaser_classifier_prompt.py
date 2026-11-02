"""project glaser classifier prompt: override por proyecto

Revision ID: 017
Revises: 016
Create Date: 2026-10-31

Añade a `proyectos` la columna `glaser_classifier_prompt`: un override opcional
del system prompt que usa el clasificador Glaser del worker heavy. Si está en
NULL (o vacío) el worker cae al prompt global (runtime.json
GLASER_CLASSIFIER_PROMPT o env GLASER_CLASSIFIER_SYSTEM) y, en última
instancia, al CLASSIFIER_SYSTEM_PROMPT integrado. Se aplica de forma
idempotente para no romper bases que ya la tengan.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, Sequence[str], None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "glaser_classifier_prompt" not in _columns("proyectos"):
        op.add_column(
            "proyectos",
            sa.Column("glaser_classifier_prompt", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if "glaser_classifier_prompt" in _columns("proyectos"):
        op.drop_column("proyectos", "glaser_classifier_prompt")
