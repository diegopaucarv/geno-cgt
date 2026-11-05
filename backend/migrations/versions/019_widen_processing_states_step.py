"""processing_states.step: ampliar a 120 para las claves de Phase B

Revision ID: 019
Revises: 018
Create Date: 2026-11-04

`transitions._maybe_trigger_phase_b` construye la clave de idempotencia como

    phase_b_run_{run_id}_n{listos}

donde `run_id` es un UUID en texto (36 caracteres). Eso da 12 + 36 + 3 = 51
caracteres contra una columna `character varying(50)`, asi que TODO INSERT
fallaba con `StringDataRightTruncation`.

El fallo no era cosmetico: la excepcion escapaba de `transition()` y el
`except` de `process_document_agents_a` la trataba como extraccion fallida,
devolviendo el documento a 'segmentado' (`fail_to`) aunque los incidentes ya
estaban commiteados. Consecuencia: nunca se podia llegar a 3 documentos en
'estado' terminal, Phase B jamas se disparaba y los documentos quedaban
"segmentados" con incidentes huerfanos.

Se amplia a 120 para dejar holgura a futuras claves por lote.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: Union[str, Sequence[str], None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "processing_states",
        "step",
        existing_type=sa.String(length=50),
        type_=sa.String(length=120),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "processing_states",
        "step",
        existing_type=sa.String(length=120),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
