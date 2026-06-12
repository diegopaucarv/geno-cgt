import logging
import os
from typing import List

import httpx

logger = logging.getLogger(__name__)


class TEIClient:
    """
    Cliente asíncrono para comunicarse con el contenedor local de Text Embeddings Inference.
    Configurado específicamente para las convenciones de voyage-4-nano.
    """

    def __init__(self, base_url: str = None):
        # Busca la variable de entorno, si no, asume el contenedor local en Docker
        self.base_url = base_url or os.environ.get("TEI_URL", "http://localhost:8080")

        # Prefijos asimétricos exigidos por Voyage 4 para optimizar la similitud del coseno
        self.query_prefix = "Represent the query for retrieving supporting documents: "
        self.document_prefix = "Represent the document for retrieval: "

    async def _embed_batch(
        self, texts: List[str], prefix: str = ""
    ) -> List[List[float]]:
        """Llamada base al servidor TEI."""
        if not texts:
            return []

        # Añadimos el prefijo matemático requerido por Voyage
        prefixed_texts = [f"{prefix}{text}" for text in texts]

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/embed",
                    json={
                        "inputs": prefixed_texts,
                        "truncate": True,  # Voyage tiene 32K de contexto, pero es seguro truncar por precaución
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                # TEI devuelve directamente un array de arrays de floats
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error al conectar con TEI: {e}")
                raise Exception(f"Fallo en generación de embeddings: {str(e)}")

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Usa esto cuando guardes Segmentos, Categorías o Memos en PostgreSQL."""
        return await self._embed_batch(documents, prefix=self.document_prefix)

    async def embed_query(self, query: str) -> List[float]:
        """Usa esto cuando un usuario o un agente busque en el corpus."""
        results = await self._embed_batch([query], prefix=self.query_prefix)
        return results[0]
