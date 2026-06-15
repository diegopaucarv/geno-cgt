"""
Caché de embeddings en Redis. Reduce llamadas al TEI en 40-60% (Plan Fase 5.1).

Clave: SHA-256(texto + model_id)
TTL por tipo de contenido (Plan Fase 9):
  - 'segment':  24h (estable, el texto del segmento no cambia)
  - 'query':    30min (volátil, el usuario pregunta cosas distintas)
  - 'prototype': 2h (intermedio, los prototipos se actualizan ocasionalmente)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Awaitable, Callable, List, Union, cast

import redis.asyncio as redis  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
TEI_MODEL_ID = os.getenv("TEI_MODEL_ID", "voyageai/voyage-4-nano")

TTL_MAP: dict[str, int] = {
    "segment": 86400,
    "query": 1800,
    "prototype": 7200,
}

# compute_fn puede ser síncrona o asíncrona
ComputeFn = Callable[
    [List[str]],
    Union[List[List[float]], Awaitable[List[List[float]]]],
]


class SharedEmbeddingCache:
    """Caché de embeddings con Redis. Single source of truth: TEI, pero Redis evita recalcular."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or REDIS_URL
        self._redis: redis.Redis | None = None
        self._model_id = TEI_MODEL_ID

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                db=1,
                decode_responses=False,
            )
        return self._redis

    def _key(self, text: str) -> str:
        digest = hashlib.sha256(f"{text}|{self._model_id}".encode("utf-8")).hexdigest()
        return f"emb:{digest}"

    async def get_or_compute(
        self,
        texts: List[str],
        content_type: str,
        compute_fn: ComputeFn,
    ) -> List[List[float]]:
        """
        Para cada texto: busca en Redis. Si está en caché → lo devuelve.
        Si no → llama a compute_fn (síncrono o asíncrono), guarda en Redis, y devuelve.
        """
        if not texts:
            return []

        r = await self._get_redis()
        keys = [self._key(t) for t in texts]

        # ── Batch read from Redis ──────────────────────────
        cached_raw = await r.mget(keys)

        results: List[List[float] | None] = [None] * len(texts)
        missing_indices: List[int] = []
        missing_texts: List[str] = []

        for i, raw in enumerate(cached_raw):
            if raw is not None:
                results[i] = json.loads(raw)
            else:
                missing_indices.append(i)
                missing_texts.append(texts[i])

        # ── Batch compute missing via TEI ──────────────────
        if missing_texts:
            logger.debug(
                "EmbeddingCache miss: %d/%d (%.0f%%)",
                len(missing_texts),
                len(texts),
                len(missing_texts) / len(texts) * 100,
            )
            result = compute_fn(missing_texts)
            if hasattr(result, "__await__"):
                vectors: List[List[float]] = await result  # type: ignore[assignment]
            else:
                vectors = cast(List[List[float]], result)

            # Batch write to Redis
            ttl = TTL_MAP.get(content_type, 3600)
            pipe = r.pipeline()
            for idx, vec in zip(missing_indices, vectors):
                pipe.setex(keys[idx], ttl, json.dumps(vec))
                results[idx] = vec
            await pipe.execute()

        return results  # type: ignore[return-value]

    async def get_or_compute_single(
        self,
        text: str,
        content_type: str,
        compute_fn: ComputeFn,
    ) -> List[float]:
        """Versión de conveniencia para un solo texto."""
        results = await self.get_or_compute([text], content_type, compute_fn)
        return results[0]
