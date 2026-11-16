"""extracted_incidents.segmento_id: se jubila como cita primaria

Revision ID: 021
Revises: 020
Create Date: 2026-11-16

`extracted_incidents.segmento_id` era la "cita primaria" denormalizada del
modelo viejo "un incidente = un segmento". Desde la 020, `incident_segmentos`
es la UNICA fuente de verdad de que texto sostiene un incidente: una fila por
par incidente/segmento y, en cada fila, su propia `tipo_dato_glaser` (NULL =
heredar la del segmento). La columna ya no transporta informacion: el extractor
no la escribe (queda NULL) y ningun lector debe leerla como "la" cita.

Esta migracion la jubila pasandola a nullable, sin borrarla: hay rutas antiguas
que aun podrian leerla, y borrar la columna queda para otra migracion cuando
esas rutas ya no existan.

Es idempotente: comprueba `is_nullable` en `information_schema.columns` antes de
alterar la columna, asi que puede correrse dos veces sin efecto adicional.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: Union[str, Sequence[str], None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── segmento_id deja de ser obligatoria ───────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'extracted_incidents'
                  AND column_name = 'segmento_id'
                  AND is_nullable = 'NO'
            ) THEN
                ALTER TABLE extracted_incidents
                    ALTER COLUMN segmento_id DROP NOT NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Revertir a NOT NULL solo es posible si nadie escribio NULLs. Tras la 021
    # el extractor deja la columna NULL por diseno, asi que en la practica este
    # downgrade es irreversible: si hay NULLs no se toca la columna (ponerle
    # NOT NULL fallaria y dejaria la migracion a medias). El caso "sin NULLs"
    # se protege ademas con `is_nullable` para seguir siendo idempotente.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'extracted_incidents'
                  AND column_name = 'segmento_id'
                  AND is_nullable = 'YES'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM extracted_incidents WHERE segmento_id IS NULL
                ) THEN
                    ALTER TABLE extracted_incidents
                        ALTER COLUMN segmento_id SET NOT NULL;
                END IF;
            END IF;
        END $$;
        """
    )
