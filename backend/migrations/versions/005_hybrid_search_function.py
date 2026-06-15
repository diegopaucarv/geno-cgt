"""hybrid_search_function

Revision ID: 005
Revises: 004
Create Date: 2026-06-14

Función SQL para búsqueda híbrida BM25 + cosine similarity.
Pesos configurables: semantic_weight + lexical_weight.
Usa los índices HNSW (vector) y GIN (tsvector) creados en migraciones anteriores.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION hybrid_search(
            query_text TEXT,
            query_embedding VECTOR(1024),
            proyecto_id UUID,
            top_k INT DEFAULT 5,
            semantic_weight FLOAT DEFAULT 0.7,
            lexical_weight FLOAT DEFAULT 0.3
        ) RETURNS TABLE(
            segmento_id UUID,
            texto TEXT,
            documento_id UUID,
            score FLOAT
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                s.id,
                s.texto,
                s.documento_id,
                (1.0 - (s.embedding <=> query_embedding)) * semantic_weight +
                COALESCE(
                    ts_rank(s.texto_tsv, plainto_tsquery('spanish', query_text)),
                    0.0
                ) * lexical_weight
                AS hybrid_score
            FROM segmentos s
            JOIN documentos d ON s.documento_id = d.id
            WHERE d.proyecto_id = proyecto_id
              AND s.embedding IS NOT NULL
            ORDER BY hybrid_score DESC
            LIMIT top_k;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS hybrid_search;")
