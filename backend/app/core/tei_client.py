# backend/app/core/tei_client.py
import asyncio
import logging
import os
from typing import List

import httpx
from app.core.embedding_cache import SharedEmbeddingCache

logger = logging.getLogger(__name__)


class TEIClient:
    """
    Cliente asíncrono para comunicarse con el contenedor TEI (ONNX).
    Los prefijos Voyage los gestiona el servidor vía prompt_name.
    Usa SharedEmbeddingCache para reducir llamadas al TEI en 40-60%.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.environ.get("TEI_URL", "http://localhost:8080")
        self._cache = SharedEmbeddingCache()

    async def _embed_batch(
        self, texts: List[str], prompt_name: str | None = None
    ) -> List[List[float]]:
        if not texts:
            return []

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/embeddings",
                    json={
                        "input": texts,
                        "model": "voyageai/voyage-4-nano",
                        "prompt_name": prompt_name,
                    },
                    timeout=120.0,
                )
                response.raise_for_status()
                data = response.json()["data"]
                return [item["embedding"] for item in data]

            except httpx.HTTPError as e:
                logger.error(f"Error al conectar con TEI: {e}")
                raise Exception(f"Fallo en generación de embeddings: {str(e)}")

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Para Segmentos, Categorías o Memos. Cachea en Redis (TTL 24h)."""
        return await self._cache.get_or_compute(
            documents,
            content_type="segment",
            compute_fn=lambda texts: self._embed_batch(texts, prompt_name=None),
        )

    async def embed_query(self, query: str) -> List[float]:
        """Para búsqueda semántica. Cachea en Redis (TTL 30min)."""
        return await self._cache.get_or_compute_single(
            query,
            content_type="query",
            compute_fn=lambda texts: self._embed_batch(texts, prompt_name="query"),
        )

    # --- Wrappers síncronos para Celery / código no-async ---

    def embed_documents_sync(self, documents: List[str]) -> List[List[float]]:
        """Versión síncrona de embed_documents para tareas Celery."""
        return asyncio.run(self.embed_documents(documents))

    def embed_query_sync(self, query: str) -> List[float]:
        """Versión síncrona de embed_query para tareas Celery."""
        return asyncio.run(self.embed_query(query))
