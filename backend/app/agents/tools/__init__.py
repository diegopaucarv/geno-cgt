"""Agent tools — funciones expuestas como herramientas para agentes.

Cada tool está decorada con @tool(name=..., description=..., parameters={...}).
El ToolRegistry las descubre automáticamente con register_from_module().

Tools disponibles:
  DB:                get_all_codes, get_code_details, get_existing_hypotheses
  Compare:           compare_embeddings, find_similar_codes (requiere TEI/Redis)
  Search:            search_segments, search_similar_codes (requiere TEI/Redis/RAG)
  ContextWindow:     expand_incident, search_precise_entities, get_document_window,
                     estimate_batch_tokens, batch_map_reduce
"""


# ── DB tools (sin dependencias externas, siempre disponibles) ────
def __getattr__(name: str):
    """Lazy imports para no forzar dependencias de TEI/Redis al importar db_tools."""
    if name in ("get_all_codes", "get_code_details", "get_existing_hypotheses"):
        from app.agents.tools import db_tools as _db

        return getattr(_db, name)
    if name in ("compare_embeddings", "find_similar_codes"):
        from app.agents.tools import compare_tools as _cmp

        return getattr(_cmp, name)
    if name in ("search_segments", "search_similar_codes"):
        from app.agents.tools import search_tools as _sch

        return getattr(_sch, name)
    if name in (
        "expand_incident",
        "search_precise_entities",
        "get_document_window",
        "estimate_batch_tokens",
        "batch_map_reduce",
        "ContextWindowManager",
    ):
        from app.agents.tools import context_window as _cw

        return getattr(_cw, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "compare_embeddings",
    "find_similar_codes",
    "get_all_codes",
    "get_code_details",
    "get_existing_hypotheses",
    "search_segments",
    "search_similar_codes",
    # ── ContextWindowManager tools ──
    "expand_incident",
    "search_precise_entities",
    "get_document_window",
    "estimate_batch_tokens",
    "batch_map_reduce",
    "ContextWindowManager",
]
