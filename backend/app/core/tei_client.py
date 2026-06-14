# backend/app/core/tei_client.py
import logging
import os
from typing import List

import httpx

logger = logging.getLogger(__name__)


class TEIClient:
    """
    Cliente asíncrono para comunicarse con el contenedor TEI (ONNX).
    Los prefijos Voyage los gestiona el servidor vía prompt_name.
    """

    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get("TEI_URL", "http://localhost:8080")

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
        """Para Segmentos, Categorías o Memos. El servidor aplica el prefijo de documento."""
        return await self._embed_batch(documents, prompt_name=None)

    async def embed_query(self, query: str) -> List[float]:
        """Para búsqueda semántica. El servidor aplica el prefijo de query."""
        results = await self._embed_batch([query], prompt_name="query")
        return results[0]

    # --- Wrappers síncronos para Celery / código no-async ---

    def embed_documents_sync(self, documents: List[str]) -> List[List[float]]:
        """Versión síncrona de embed_documents para tareas Celery."""
        import asyncio

        return asyncio.run(self.embed_documents(documents))

    def embed_query_sync(self, query: str) -> List[float]:
        """Versión síncrona de embed_query para tareas Celery."""
        import asyncio

        return asyncio.run(self.embed_query(query))
