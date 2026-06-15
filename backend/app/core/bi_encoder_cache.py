"""Caché de prototipos de código (Bi-encoder) en Redis.

Plan §2.2: El Bi-encoder Similarity Cache acelera la recomendación de códigos
evitando que cada nuevo segmento se compare contra todos los centroides en pgvector.

Estrategia:
  1. Cada código tiene hasta 3 segmentos ejemplares (CodePrototype.segment_ids)
  2. El embedding del prototipo se cachea en Redis (TTL 2h)
  3. Al recomendar códigos para un segmento nuevo:
     - Primero se compara contra prototipos cacheados (O(1) lookup)
     - Si no hay prototipo en Redis → fallback a pgvector cosine distance
  4. build_prototype_cache() se ejecuta tras cada batch de codificación (B2)

Reducción estimada de consultas pgvector: 40-60% (Plan Fase 5.1).
"""

from __future__ import annotations

import json
import logging
from typing import List
from uuid import UUID

import redis.asyncio as redis
from app.core.tei_client import TEIClient

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379"
PROTOTYPE_TTL = 7200  # 2h (Plan Fase 9)
PROTOTYPE_PREFIX = "proto:"


class BiEncoderCache:
    """
    Caché de embeddings de prototipos de código en Redis.

    Clave: proto:{code_id}
    Valor: JSON con {embedding: [...], segment_ids: [...], updated_at: ...}
    """

    def __init__(
        self, redis_url: str | None = None, tei: TEIClient | None = None
    ) -> None:
        self._redis_url = redis_url or REDIS_URL
        self._redis: redis.Redis | None = None
        self._tei = tei or TEIClient()

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, db=1, decode_responses=False)
        return self._redis

    # ═══════════════════════════════════════════════════════════
    # Operaciones atómicas
    # ═══════════════════════════════════════════════════════════

    async def get_prototype(self, code_id: UUID) -> dict | None:
        """
        Recupera el prototipo cacheado de un código.

        Returns:
            dict con {embedding, segment_ids, updated_at} o None si no está.
        """
        r = await self._get_redis()
        raw = await r.get(f"{PROTOTYPE_PREFIX}{code_id}")
        if raw is None:
            return None
        return json.loads(raw)

    async def set_prototype(
        self,
        code_id: UUID,
        segment_ids: List[str],
        centroid: List[float],
    ) -> None:
        """
        Guarda (o actualiza) el prototipo de un código en Redis.

        Args:
            code_id: UUID de la categoría.
            segment_ids: IDs de los 1-3 segmentos ejemplares.
            centroid: Embedding promedio de los segmentos ejemplares.
        """
        import datetime

        r = await self._get_redis()
        payload = json.dumps(
            {
                "embedding": centroid,
                "segment_ids": segment_ids,
                "updated_at": datetime.datetime.utcnow().isoformat(),
            }
        )
        await r.setex(f"{PROTOTYPE_PREFIX}{code_id}", PROTOTYPE_TTL, payload)
        logger.debug("Prototype cached: code=%s, segments=%s", code_id, segment_ids)

    async def delete_prototype(self, code_id: UUID) -> None:
        """Elimina el prototipo de Redis (cuando un código se divide o fusiona)."""
        r = await self._get_redis()
        await r.delete(f"{PROTOTYPE_PREFIX}{code_id}")

    async def get_all_prototypes(self, code_ids: List[UUID]) -> dict[UUID, dict]:
        """
        Batch read: recupera todos los prototipos para una lista de códigos.

        Returns:
            Dict[code_id → {embedding, segment_ids}] solo para los que estaban en Redis.
        """
        if not code_ids:
            return {}

        r = await self._get_redis()
        keys = [f"{PROTOTYPE_PREFIX}{cid}" for cid in code_ids]
        raw_list = await r.mget(keys)

        result: dict[UUID, dict] = {}
        for cid, raw in zip(code_ids, raw_list):
            if raw is not None:
                result[cid] = json.loads(raw)

        return result

    # ═══════════════════════════════════════════════════════════
    # Construcción del caché (llamado tras B2 — codificación)
    # ═══════════════════════════════════════════════════════════

    async def build_prototype_cache(self, proyecto_id: UUID, db_session) -> int:
        """
        Reconstruye el caché de prototipos para todos los códigos de un proyecto.

        Para cada código:
          1. Selecciona 1-3 segmentos ejemplares (los de mayor confianza)
          2. Calcula el embedding promedio (centroide)
          3. Guarda en Redis

        Llamado tras cada batch de B2 (open coding).

        Returns:
            Número de prototipos cacheados.
        """
        from sqlalchemy import text

        # Obtener códigos con segmentos asignados (confianza > 0.7)
        rows = await db_session.execute(
            text("""
                SELECT cs.categoria_id, cs.segmento_id, cs.confianza
                FROM codigos_segmento cs
                JOIN categorias c ON cs.categoria_id = c.id
                WHERE c.proyecto_id = :pid
                  AND cs.confianza > 0.7
                ORDER BY cs.categoria_id, cs.confianza DESC
            """),
            {"pid": proyecto_id},
        )
        all_rows = rows.fetchall()

        if not all_rows:
            return 0

        # Agrupar por código, tomar top 3
        code_segments: dict[UUID, list[str]] = {}
        for row in all_rows:
            code_id = row[0]
            seg_id = str(row[1])
            if code_id not in code_segments:
                code_segments[code_id] = []
            if len(code_segments[code_id]) < 3:
                code_segments[code_id].append(seg_id)

        # Para cada código, calcular centroide y cachear
        cached = 0
        for code_id, seg_ids in code_segments.items():
            # Obtener embeddings de los segmentos
            seg_rows = await db_session.execute(
                text(
                    "SELECT embedding FROM segmentos WHERE id = ANY(:ids) AND embedding IS NOT NULL"
                ),
                {"ids": seg_ids},
            )
            embeddings = [r[0] for r in seg_rows.fetchall()]

            if not embeddings:
                continue

            # Calcular centroide (promedio simple)
            dim = len(embeddings[0])
            centroid = [
                sum(e[i] for e in embeddings) / len(embeddings) for i in range(dim)
            ]

            await self.set_prototype(code_id, seg_ids, centroid)
            cached += 1

        logger.info(
            "Prototype cache built: %d codes cached for project %s",
            cached,
            proyecto_id,
        )
        return cached

    # ═══════════════════════════════════════════════════════════
    # Búsqueda rápida por similitud (alternativa a pgvector)
    # ═══════════════════════════════════════════════════════════

    async def find_similar_codes(
        self,
        segment_embedding: List[float],
        code_ids: List[UUID],
        top_k: int = 5,
        threshold: float = 0.6,
    ) -> List[dict]:
        """
        Busca códigos similares usando solo los prototipos cacheados.

        Si un código no está en Redis, se omite (el caller debe hacer
        fallback a pgvector para esos).

        Returns:
            [{code_id, score}, ...] ordenados por similitud descendente.
        """
        prototypes = await self.get_all_prototypes(code_ids)

        if not prototypes:
            return []

        scored = []
        for code_id, proto in prototypes.items():
            proto_emb = proto.get("embedding")
            if proto_emb is None:
                continue

            # Cosine similarity (asumiendo vectores normalizados)
            score = sum(a * b for a, b in zip(segment_embedding, proto_emb))

            if score >= threshold:
                scored.append(
                    {
                        "code_id": str(code_id),
                        "score": round(score, 4),
                        "segment_ids": proto.get("segment_ids", []),
                        "from_cache": True,
                    }
                )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]
