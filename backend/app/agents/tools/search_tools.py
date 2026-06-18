"""Search tools — búsqueda RAG de segmentos y códigos.

Usan RAGService (RRF: semantic + lexical) y TEI (embeddings).
Son las tools más poderosas para agentes que necesitan evidencia textual.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.agents.tool_registry import tool
from app.core.tei_client import TEIClient

logger = logging.getLogger(__name__)

tei = TEIClient()


def _run_async(coro):
    """Helper: ejecuta coroutine en event loop. Seguro desde sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════
# Tools
# ═══════════════════════════════════════════════════════════════════


@tool(
    name="search_segments",
    description="Busca segmentos semánticamente en el corpus del proyecto "
    "usando RRF (Reciprocal Rank Fusion: búsqueda semántica + "
    "léxica). Devuelve los segmentos más relevantes con su score. "
    "Útil para encontrar evidencia textual sobre cualquier tema "
    "o patrón mencionado en los documentos.",
    parameters={
        "query": "texto de búsqueda en lenguaje natural "
        "(ej: 'negociando límites con el algoritmo')",
        "proyecto_id": "UUID del proyecto (obligatorio)",
        "top_k": "número de resultados (default: 5, max: 10)",
    },
)
def search_segments(query: str, proyecto_id: str, top_k: int = 5) -> list:
    """Tool: búsqueda RAG de segmentos con RRF + MMR."""
    from app.db.database import AsyncSessionLocal
    from app.services.rag import RAGService

    async def _search():
        async with AsyncSessionLocal() as db:
            service = RAGService(db, tei)
            results = await service.search(
                query=query,
                proyecto_id=UUID(proyecto_id),
                top_k=min(top_k, 10),
                fusion="rrf",
            )
            return [
                {
                    "segmento_id": str(r.segmento_id),
                    "texto": r.texto[:300],
                    "documento_id": str(r.documento_id),
                    "documento_nombre": r.documento_nombre,
                    "score": r.score,
                }
                for r in results
            ]

    try:
        return _run_async(_search())
    except Exception as e:
        logger.error("search_segments failed: %s", e)
        return [{"error": str(e)}]


@tool(
    name="search_similar_codes",
    description="Busca códigos existentes semánticamente similares a un "
    "texto dado (nombre + definición de un código candidato). "
    "Usa el centroide del código en pgvector (HNSW). "
    "Útil para verificar si un nuevo código ya existe con otro nombre.",
    parameters={
        "text": "definición o descripción del código a comparar",
        "proyecto_id": "UUID del proyecto",
        "top_k": "número de resultados (default: 5)",
    },
)
def search_similar_codes(text: str, proyecto_id: str, top_k: int = 5) -> list:
    """Tool: búsqueda de códigos por similitud de embedding."""
    from app.db.database import AsyncSessionLocal
    from app.services.rag import RAGService

    async def _search():
        async with AsyncSessionLocal() as db:
            embedding = await tei.embed_query(text)
            service = RAGService(db, tei)
            results = await service.search_similar_codes(
                segment_embedding=embedding,
                proyecto_id=UUID(proyecto_id),
                top_k=min(top_k, 10),
            )
            return [
                {
                    "id": c.id,
                    "nombre": c.nombre,
                    "definicion": (c.definicion or "")[:200],
                    "score": c.score,
                }
                for c in results
            ]

    try:
        return _run_async(_search())
    except Exception as e:
        logger.error("search_similar_codes failed: %s", e)
        return [{"error": str(e)}]
