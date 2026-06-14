"""
Cliente HTTP síncrono para el endpoint TEI /v1/embeddings.

Uso:
    from embedding_client import EmbeddingClient
    client = EmbeddingClient()
    vecs = client.encode(["texto 1", "texto 2"])  # np.ndarray (N, 1024)
    vec  = client.encode_single("texto")           # np.ndarray (1024,)

El TEI_URL se lee de la variable de entorno (default: http://tei:8080).
"""

import os

import numpy as np
import requests

TEI_URL = os.getenv("TEI_URL", "http://tei:8080")
MODEL_ID = os.getenv("MODEL_ID", "voyageai/voyage-4-nano")


class EmbeddingClient:
    """Cliente síncrono para TEI embeddings (Voyage-4 ONNX, 1024-dim)."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or TEI_URL
        self.model = MODEL_ID

    def encode(self, texts: list[str], prompt_name: str | None = None) -> np.ndarray:
        """Codifica una lista de textos → array (N, dim)."""
        if not texts:
            return np.empty((0, 1024), dtype=np.float32)

        response = requests.post(
            f"{self.base_url}/v1/embeddings",
            json={
                "input": texts,
                "model": self.model,
                "prompt_name": prompt_name,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        embeddings = [item["embedding"] for item in data]
        return np.array(embeddings, dtype=np.float32)

    def encode_single(self, text: str) -> np.ndarray:
        """Codifica un solo texto → array (dim,)."""
        return self.encode([text])[0]
