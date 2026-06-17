"""
Servicio RAG con RRF (Reciprocal Rank Fusion) + MMR opcional.

Estrategia de dos fases:
  Fase 1 (SQL):  RRF fusiona rankings semántico y léxico. Sin normalizar scores.
  Fase 2 (Python): MMR reordena para diversidad. Opera sobre ≤ 50 candidatos.

Modos de fusión:
  - 'rrf':             Reciprocal Rank Fusion (k=60, configurable)
  - 'semantic':        solo cosine similarity (índice HNSW)
  - 'lexical':         solo BM25 (ts_rank + índice GIN)

Casos de uso:
  1. search()               — búsqueda general (usuario final)
  2. search_similar_codes() — code recommendation (siempre semántico puro)
  3. search_context_for_code() — context retrieval para Map-Reduce (RRF + MMR)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Literal
from uuid import UUID

from app.core.tei_client import TEIClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FusionMode = Literal["rrf", "semantic", "lexical"]


@dataclass
class RAGResult:
    segmento_id: UUID
    texto: str
    documento_id: UUID
    documento_nombre: str = ""
    score: float = 0.0
    mmr_score: float | None = None
    _embedding: List[float] | None = field(default=None, repr=False)


@dataclass
class CodeCandidate:
    id: str
    nombre: str
    definicion: str
    score: float


class RAGService:
    """
    Motor RAG con fusión configurable + MMR opcional + filtro de near-duplicates.

    Principios de diseño:
      - Sin dependencias externas (solo Python stdlib + SQLAlchemy + TEI).
      - La precisión semántica viene del embedding enriquecido al indexar,
        no del algoritmo de fusión.
      - MMR es opcional y opera sobre ≤ 50 candidatos en Python puro.
    """

    RRF_K = 60
    EXPANSION_FACTOR = 5
    DUPLICATE_THRESHOLD = 0.92
    DEFAULT_LAMBDA = 0.7

    def __init__(self, db: AsyncSession, tei: TEIClient) -> None:
        self.db = db
        self.tei = tei

    # ═══════════════════════════════════════════════════════════
    # API Pública
    # ═══════════════════════════════════════════════════════════

    async def search(
        self,
        query: str,
        proyecto_id: UUID,
        top_k: int = 5,
        fusion: FusionMode = "rrf",
        diversify: bool = False,
        lambda_mmr: float = DEFAULT_LAMBDA,
        rrf_k: int = RRF_K,
        documento_id: UUID | None = None,
    ) -> List[RAGResult]:
        n_candidates = top_k * self.EXPANSION_FACTOR if diversify else top_k

        candidates = await self._retrieve(
            query=query,
            proyecto_id=proyecto_id,
            top_k=n_candidates,
            fusion=fusion,
            rrf_k=rrf_k,
            documento_id=documento_id,
        )

        if diversify and len(candidates) > top_k:
            candidates = self._mmr_rerank(candidates, top_k, lambda_=lambda_mmr)

        return candidates[:top_k]

    async def search_similar_codes(
        self,
        segment_embedding: List[float],
        proyecto_id: UUID,
        top_k: int = 5,
    ) -> List[CodeCandidate]:
        sql = text("""
            SELECT c.id, c.nombre, c.definicion,
                   1.0 - (c.embedding_centroide <=> :query_vec) AS score
            FROM categorias c
            WHERE c.proyecto_id = :proyecto_id
              AND c.embedding_centroide IS NOT NULL
            ORDER BY score DESC
            LIMIT :top_k
        """)
        result = await self.db.execute(
            sql,
            {
                "query_vec": segment_embedding,
                "proyecto_id": proyecto_id,
                "top_k": top_k,
            },
        )
        return [
            CodeCandidate(
                id=str(r[0]), nombre=r[1], definicion=r[2], score=round(float(r[3]), 4)
            )
            for r in result.fetchall()
        ]

    async def search_context_for_code(
        self,
        code_id: UUID,
        proyecto_id: UUID,
        top_k: int = 10,
        lambda_mmr: float = 0.6,
    ) -> List[RAGResult]:
        code_info = await self._get_code_centroid(code_id)
        if code_info is None:
            return []

        n_candidates = top_k * self.EXPANSION_FACTOR
        candidates = await self._retrieve(
            query=code_info["nombre"] + " " + code_info["definicion"],
            proyecto_id=proyecto_id,
            top_k=n_candidates,
            fusion="rrf",
            rrf_k=self.RRF_K,
            query_vec_override=code_info["centroid"],
        )

        if len(candidates) > top_k:
            candidates = self._mmr_rerank(candidates, top_k, lambda_=lambda_mmr)

        return candidates[:top_k]

    # ═══════════════════════════════════════════════════════════
    # Fase 1 — Retrieval
    # ═══════════════════════════════════════════════════════════

    async def _retrieve(
        self,
        query: str,
        proyecto_id: UUID,
        top_k: int,
        fusion: FusionMode,
        rrf_k: int = RRF_K,
        documento_id: UUID | None = None,
        query_vec_override: List[float] | None = None,
    ) -> List[RAGResult]:
        if query_vec_override is not None:
            query_vec = query_vec_override
        else:
            query_vec = await self.tei.embed_query(query)

        if fusion == "rrf":
            return await self._retrieve_rrf(
                query, query_vec, proyecto_id, top_k, rrf_k, documento_id
            )
        elif fusion == "semantic":
            return await self._retrieve_semantic(
                query_vec, proyecto_id, top_k, documento_id
            )
        else:
            return await self._retrieve_lexical(query, proyecto_id, top_k, documento_id)

    async def _retrieve_rrf(
        self,
        query_text: str,
        query_vec: List[float],
        proyecto_id: UUID,
        top_k: int,
        rrf_k: int,
        documento_id: UUID | None,
    ) -> List[RAGResult]:
        if documento_id is not None:
            sql = text("""
                WITH semantic_rank AS (
                    SELECT s.id, s.texto, s.documento_id, s.embedding,
                           ROW_NUMBER() OVER (ORDER BY s.embedding <=> :query_vec) AS rank
                    FROM segmentos s
                    WHERE s.documento_id = :doc_id AND s.embedding IS NOT NULL
                ),
                lexical_rank AS (
                    SELECT s.id,
                           ROW_NUMBER() OVER (
                               ORDER BY ts_rank(s.texto_tsv,
                                   plainto_tsquery('spanish', :query_text)) DESC
                           ) AS rank
                    FROM segmentos s
                    WHERE s.documento_id = :doc_id
                ),
                rrf AS (
                    SELECT sr.id, sr.texto, sr.documento_id, sr.embedding,
                           COALESCE(1.0 / (:rrf_k + sr.rank), 0.0) +
                           COALESCE(1.0 / (:rrf_k + lr.rank), 0.0) AS score
                    FROM semantic_rank sr
                    LEFT JOIN lexical_rank lr ON sr.id = lr.id
                )
                SELECT rrf.id, rrf.texto, rrf.documento_id,
                       d.original_filename AS documento_nombre,
                       rrf.embedding, rrf.score
                FROM rrf
                JOIN documentos d ON rrf.documento_id = d.id
                ORDER BY rrf.score DESC LIMIT :top_k
            """)
            params = {
                "query_vec": query_vec,
                "query_text": query_text,
                "doc_id": documento_id,
                "rrf_k": float(rrf_k),
                "top_k": top_k,
            }
        else:
            sql = text("""
                WITH semantic_rank AS (
                    SELECT s.id, s.texto, s.documento_id, s.embedding,
                           ROW_NUMBER() OVER (ORDER BY s.embedding <=> :query_vec) AS rank
                    FROM segmentos s
                    JOIN documentos d ON s.documento_id = d.id
                    WHERE d.proyecto_id = :proyecto_id AND s.embedding IS NOT NULL
                ),
                lexical_rank AS (
                    SELECT s.id,
                           ROW_NUMBER() OVER (
                               ORDER BY ts_rank(s.texto_tsv,
                                   plainto_tsquery('spanish', :query_text)) DESC
                           ) AS rank
                    FROM segmentos s
                    JOIN documentos d ON s.documento_id = d.id
                    WHERE d.proyecto_id = :proyecto_id
                ),
                rrf AS (
                    SELECT sr.id, sr.texto, sr.documento_id, sr.embedding,
                           COALESCE(1.0 / (:rrf_k + sr.rank), 0.0) +
                           COALESCE(1.0 / (:rrf_k + lr.rank), 0.0) AS score
                    FROM semantic_rank sr
                    LEFT JOIN lexical_rank lr ON sr.id = lr.id
                )
                SELECT rrf.id, rrf.texto, rrf.documento_id,
                       d.original_filename AS documento_nombre,
                       rrf.embedding, rrf.score
                FROM rrf
                JOIN documentos d ON rrf.documento_id = d.id
                ORDER BY rrf.score DESC LIMIT :top_k
            """)
            params = {
                "query_vec": query_vec,
                "query_text": query_text,
                "proyecto_id": proyecto_id,
                "rrf_k": float(rrf_k),
                "top_k": top_k,
            }

        result = await self.db.execute(sql, params)
        return [
            RAGResult(
                segmento_id=r[0],
                texto=r[1],
                documento_id=r[2],
                documento_nombre=r[3],
                score=round(float(r[5]), 4),
                _embedding=r[4],
            )
            for r in result.fetchall()
        ]

    async def _retrieve_semantic(
        self,
        query_vec: List[float],
        proyecto_id: UUID,
        top_k: int,
        documento_id: UUID | None,
    ) -> List[RAGResult]:
        if documento_id is not None:
            sql = text("""
                SELECT s.id, s.texto, s.documento_id, d.original_filename AS documento_nombre,
                       s.embedding,
                       1.0 - (s.embedding <=> :query_vec) AS score
                FROM segmentos s
                JOIN documentos d ON s.documento_id = d.id
                WHERE s.documento_id = :doc_id AND s.embedding IS NOT NULL
                ORDER BY score DESC LIMIT :top_k
            """)
            params = {"query_vec": query_vec, "doc_id": documento_id, "top_k": top_k}
        else:
            sql = text("""
                SELECT s.id, s.texto, s.documento_id, d.original_filename AS documento_nombre,
                       s.embedding,
                       1.0 - (s.embedding <=> :query_vec) AS score
                FROM segmentos s
                JOIN documentos d ON s.documento_id = d.id
                WHERE d.proyecto_id = :proyecto_id AND s.embedding IS NOT NULL
                ORDER BY score DESC LIMIT :top_k
            """)
            params = {
                "query_vec": query_vec,
                "proyecto_id": proyecto_id,
                "top_k": top_k,
            }

        result = await self.db.execute(sql, params)
        return [
            RAGResult(
                segmento_id=r[0],
                texto=r[1],
                documento_id=r[2],
                documento_nombre=r[3],
                score=round(float(r[5]), 4),
                _embedding=r[4],
            )
            for r in result.fetchall()
        ]

    async def _retrieve_lexical(
        self,
        query_text: str,
        proyecto_id: UUID,
        top_k: int,
        documento_id: UUID | None,
    ) -> List[RAGResult]:
        # Lexical no devuelve embedding. Para MMR no es relevante (se usa solo
        # cuando el usuario pide búsqueda puramente léxica, sin diversify).
        if documento_id is not None:
            sql = text("""
                SELECT s.id, s.texto, s.documento_id, d.original_filename AS documento_nombre,
                       ts_rank(s.texto_tsv, plainto_tsquery('spanish', :query_text)) AS score
                FROM segmentos s
                JOIN documentos d ON s.documento_id = d.id
                WHERE s.documento_id = :doc_id
                ORDER BY score DESC LIMIT :top_k
            """)
            params = {"query_text": query_text, "doc_id": documento_id, "top_k": top_k}
        else:
            sql = text("""
                SELECT s.id, s.texto, s.documento_id, d.original_filename AS documento_nombre,
                       ts_rank(s.texto_tsv, plainto_tsquery('spanish', :query_text)) AS score
                FROM segmentos s
                JOIN documentos d ON s.documento_id = d.id
                WHERE d.proyecto_id = :proyecto_id
                ORDER BY score DESC LIMIT :top_k
            """)
            params = {
                "query_text": query_text,
                "proyecto_id": proyecto_id,
                "top_k": top_k,
            }

        result = await self.db.execute(sql, params)
        return [
            RAGResult(
                segmento_id=r[0],
                texto=r[1],
                documento_id=r[2],
                documento_nombre=r[3],
                score=round(float(r[4]), 4),
            )
            for r in result.fetchall()
        ]

    async def _get_code_centroid(self, code_id: UUID) -> dict | None:
        sql = text("""
            SELECT nombre, definicion, embedding_centroide
            FROM categorias WHERE id = :code_id
        """)
        result = await self.db.execute(sql, {"code_id": code_id})
        row = result.fetchone()
        if row is None or row[2] is None:
            return None
        return {"nombre": row[0], "definicion": row[1], "centroid": row[2]}

    # ═══════════════════════════════════════════════════════════
    # Fase 2 — MMR (Python puro, math stdlib)
    # ═══════════════════════════════════════════════════════════

    def _mmr_rerank(
        self,
        candidates: List[RAGResult],
        top_k: int,
        lambda_: float = DEFAULT_LAMBDA,
    ) -> List[RAGResult]:
        """
        Maximal Marginal Relevance.

        Para cada candidato: mmr = λ·relevancia - (1-λ)·max_sim_a_seleccionados.
        Descarta candidatos con cosine > DUPLICATE_THRESHOLD (near-duplicates).
        """
        if len(candidates) <= top_k:
            for c in candidates:
                c.mmr_score = c.score
            return candidates

        # Filtrar candidatos sin embedding
        valid = [c for c in candidates if c._embedding is not None]
        if len(valid) <= top_k:
            for c in valid:
                c.mmr_score = c.score
            return valid

        selected: List[RAGResult] = []
        remaining = list(valid)

        while len(selected) < top_k and remaining:
            best_idx = -1
            best_score = -float("inf")

            for i, candidate in enumerate(remaining):
                relevance = candidate.score

                if selected:
                    max_red = max(
                        self._dot(candidate._embedding, s._embedding)  # type: ignore[arg-type]
                        for s in selected
                    )
                else:
                    max_red = 0.0

                if max_red >= self.DUPLICATE_THRESHOLD:
                    continue

                mmr_score = lambda_ * relevance - (1 - lambda_) * max_red

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            if best_idx == -1:
                break

            chosen = remaining.pop(best_idx)
            chosen.mmr_score = round(best_score, 4)
            selected.append(chosen)

        return selected

    @staticmethod
    def _dot(a: List[float], b: List[float]) -> float:
        """Producto punto. Para vectores L2-normalizados, dot = cosine similarity."""
        return sum(x * y for x, y in zip(a, b))
