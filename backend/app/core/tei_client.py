# backend/app/core/tei_client.py
import logging
import os
from typing import List

import httpx

logger = logging.getLogger(__name__)


class TEIClient:
    """
    Cliente asíncrono para comunicarse con el contenedor Infinity.
    Configurado para el modelo voyage-4-nano (dimensión nativa: 2048).
    """

    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get("TEI_URL", "http://localhost:8080")

        # Prefijos asimétricos requeridos por Voyage para optimizar la distancia matemática
        self.query_prefix = "Represent the query for retrieving supporting documents: "
        self.document_prefix = "Represent the document for retrieval: "

    async def _embed_batch(
        self, texts: List[str], prefix: str = ""
    ) -> List[List[float]]:
        if not texts:
            return []

        prefixed_texts = [f"{prefix}{text}" for text in texts]

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/embeddings",
                    json={
                        "input": prefixed_texts,
                        "model": "voyageai/voyage-4-nano",
                    },
                    timeout=120.0,  # El primer arranque tarda mientras carga los tensores a la RAM
                )
                response.raise_for_status()
                data = response.json()["data"]

                # El formato OpenAI devuelve una lista de diccionarios
                return [item["embedding"] for item in data]

            except httpx.HTTPError as e:
                logger.error(f"Error al conectar con Infinity: {e}")
                raise Exception(f"Fallo en generación de embeddings: {str(e)}")

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Usa esto para guardar Segmentos, Categorías o Memos en PostgreSQL."""
        return await self._embed_batch(documents, prefix=self.document_prefix)

    async def embed_query(self, query: str) -> List[float]:
        """Usa esto para buscar en el corpus."""
        results = await self._embed_batch([query], prefix=self.query_prefix)
        return results[0]
