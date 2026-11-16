"""incident_segmentos: un incidente cita N segmentos, cada uno con su categoria

Revision ID: 020
Revises: 019
Create Date: 2026-11-16

Hasta ahora un incidente solo podia apoyarse en UN segmento
(`extracted_incidents.segmento_id`) y su categoria Glaser era la del segmento,
no la de la cita. La curacion manual necesita lo contrario: un incidente que
cita varias frases y que puede anotar cada cita con su propia categoria (por
ejemplo una cita `vague_data` que aun asi ilustra el incidente).

Esta migracion:
  1. crea `incident_segmentos` (una fila por par incidente/segmento);
  2. anade `extracted_incidents.origen` ('ia' | 'manual'), que es lo que permite
     que una re-extraccion conserve el trabajo hecho a mano;
  3. rellena un enlace por cada `extracted_incidents.segmento_id`;
  4. rellena los enlaces adicionales que solo existian como ordinales en
     `preguntas_glaser_json.segment_refs`;
  5. reescribe esos ordinales como UUIDs y conserva los originales en
     `segment_refs_ordinals`.

Sobre (5): `segment_refs` son ordinales 1-based sobre la lista de segmentos
`baseline_data` ordenada por `posicion`, NO son `posicion`. Un lector que los
trate como `posicion` (era el caso de `workers/heavy/agents_b.py`) resuelve el
segmento equivocado, y como todos los documentos de un proyecto repiten
posiciones 1..N, un solo ordinal puede matchear un segmento en cada documento.
Reescribirlos a UUID elimina esa clase de error.

NO borra ni hace nullable `extracted_incidents.segmento_id`: ocho rutas de
borrado y tres lectores dependen de el. Queda como cita primaria denormalizada,
y `incident_segmentos` es la fuente de verdad.

Tambien cambia a CASCADE las FK que apuntan a `extracted_incidents`
(`incident_comparisons` x2) y a `segmentos` (`incident_segmentos.segmento_id`).
Estaban en NO ACTION, asi que cualquier ruta que borrara incidentes sin limpiar
antes `incident_comparisons` devolvia un 500 por violacion de FK. Habia cinco
rutas con ese bug latente; la cascada lo cierra para todas, incluidas las que se
escriban despues.

Es idempotente: cada paso se guarda por existencia previa.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: Union[str, Sequence[str], None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ORDINALS_CTE = """
    WITH ordinal AS (
        SELECT id,
               documento_id,
               row_number() OVER (
                   PARTITION BY documento_id ORDER BY posicion
               ) AS ref
        FROM segmentos
        WHERE tipo_dato_glaser = 'baseline_data'
    )
"""


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


#: FK que deben caer en cascada: (tabla, constraint, columna, ref_tabla, ref_col).
_CASCADE_FKS = (
    (
        "incident_comparisons",
        "incident_comparisons_incident_a_id_fkey",
        "incident_a_id",
        "extracted_incidents",
        "id",
    ),
    (
        "incident_comparisons",
        "incident_comparisons_incident_b_id_fkey",
        "incident_b_id",
        "extracted_incidents",
        "id",
    ),
    (
        "incident_segmentos",
        "incident_segmentos_segmento_id_fkey",
        "segmento_id",
        "segmentos",
        "id",
    ),
)


def _fk_delete_rule(table: str, constraint: str) -> str | None:
    """Devuelve 'a' (NO ACTION), 'c' (CASCADE), ... o None si no existe."""
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conrelid = (SELECT oid FROM pg_class WHERE relname = :tbl) "
                "AND conname = :name"
            ),
            {"tbl": table, "name": constraint},
        )
        .first()
    )
    return row[0] if row else None


def _set_cascade(ondelete: str) -> None:
    """Deja cada FK de :data:`_CASCADE_FKS` con la regla de borrado pedida."""
    code = {"CASCADE": "c", "NO ACTION": "a"}[ondelete]
    tables = _tables()
    for table, constraint, column, ref_table, ref_column in _CASCADE_FKS:
        if table not in tables:
            continue
        current = _fk_delete_rule(table, constraint)
        if current == code:
            continue
        if current is not None:
            op.drop_constraint(constraint, table, type_="foreignkey")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column}) "
            f"ON DELETE {ondelete}"
        )


def upgrade() -> None:
    if "incident_segmentos" not in _tables():
        op.create_table(
            "incident_segmentos",
            sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("segmento_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tipo_dato_glaser", sa.String(length=50), nullable=True),
            sa.Column(
                "is_manual", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "creado_en",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["incident_id"], ["extracted_incidents.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["segmento_id"], ["segmentos.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("incident_id", "segmento_id"),
        )
        op.create_index(
            "ix_incident_segmentos_segmento_id",
            "incident_segmentos",
            ["segmento_id"],
        )

    if "origen" not in _columns("extracted_incidents"):
        op.execute(
            "ALTER TABLE extracted_incidents "
            "ADD COLUMN origen varchar(20) NOT NULL DEFAULT 'ia'"
        )

    # ── 3. Un enlace por incidente: su cita primaria ──────────────────
    op.execute(
        """
        INSERT INTO incident_segmentos
            (incident_id, segmento_id, tipo_dato_glaser, is_manual)
        SELECT ei.id, ei.segmento_id, NULL, false
        FROM extracted_incidents ei
        JOIN segmentos s ON s.id = ei.segmento_id
        ON CONFLICT (incident_id, segmento_id) DO NOTHING
        """
    )

    # ── 4. Enlaces que solo existian como ordinales ───────────────────
    op.execute(
        _ORDINALS_CTE
        + """
        , pairs AS (
            SELECT ei.id AS incident_id,
                   ei.documento_id,
                   (r.value)::int AS ref
            FROM extracted_incidents ei
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE
                    WHEN jsonb_typeof(ei.preguntas_glaser_json -> 'segment_refs') = 'array'
                        THEN ei.preguntas_glaser_json -> 'segment_refs'
                    ELSE '[]'::jsonb
                END
            ) AS r(value)
            WHERE r.value ~ '^[0-9]+$'
        )
        INSERT INTO incident_segmentos
            (incident_id, segmento_id, tipo_dato_glaser, is_manual)
        SELECT p.incident_id, o.id, NULL, false
        FROM pairs p
        JOIN ordinal o
          ON o.documento_id = p.documento_id AND o.ref = p.ref
        ON CONFLICT (incident_id, segmento_id) DO NOTHING
        """
    )

    # ── 5. Ordinales -> UUIDs, conservando los originales ─────────────
    op.execute(
        _ORDINALS_CTE
        + """
        , pairs AS (
            SELECT ei.id AS incident_id,
                   ei.documento_id,
                   (r.value)::int AS ref
            FROM extracted_incidents ei
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE
                    WHEN jsonb_typeof(ei.preguntas_glaser_json -> 'segment_refs') = 'array'
                        THEN ei.preguntas_glaser_json -> 'segment_refs'
                    ELSE '[]'::jsonb
                END
            ) AS r(value)
            WHERE r.value ~ '^[0-9]+$'
        )
        , resolved AS (
            SELECT p.incident_id,
                   jsonb_agg(o.id::text ORDER BY p.ref) AS ids,
                   bool_and(o.id IS NOT NULL)          AS completo
            FROM pairs p
            LEFT JOIN ordinal o
                   ON o.documento_id = p.documento_id AND o.ref = p.ref
            GROUP BY p.incident_id
        )
        UPDATE extracted_incidents ei
        SET preguntas_glaser_json =
            jsonb_set(
                jsonb_set(
                    ei.preguntas_glaser_json,
                    '{segment_refs_ordinals}',
                    ei.preguntas_glaser_json -> 'segment_refs'
                ),
                '{segment_refs}',
                r.ids
            )
        FROM resolved r
        WHERE ei.id = r.incident_id
          AND r.completo
        """
    )

    # ── 6. Que borrar un incidente o un segmento no reviente por FK ���───
    _set_cascade("CASCADE")


def downgrade() -> None:
    # Las FK vuelven a NO ACTION: el esquema anterior no conocia cascadas.
    _set_cascade("NO ACTION")

    # Restaura los ordinales que se conservaron antes de reescribirlos.
    op.execute(
        """
        UPDATE extracted_incidents
        SET preguntas_glaser_json =
            jsonb_set(
                preguntas_glaser_json,
                '{segment_refs}',
                preguntas_glaser_json -> 'segment_refs_ordinals'
            ) - 'segment_refs_ordinals'
        WHERE preguntas_glaser_json ? 'segment_refs_ordinals'
        """
    )

    if "incident_segmentos" in _tables():
        op.drop_index(
            "ix_incident_segmentos_segmento_id", table_name="incident_segmentos"
        )
        op.drop_table("incident_segmentos")

    if "origen" in _columns("extracted_incidents"):
        op.execute("ALTER TABLE extracted_incidents DROP COLUMN origen")
