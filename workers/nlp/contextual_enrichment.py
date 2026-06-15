"""
Enriquecimiento contextual para embeddings de segmentos.

Inspirado en Anthropic Contextual Retrieval (Sep 2024).
Añade contexto del documento, fuente, resumen global y segmento previo
al texto antes de embeberlo, mejorando la precisión polisemántica.

El enriquecimiento ocurre UNA vez al indexar. No afecta la búsqueda.
"""

from __future__ import annotations

from typing import List, Optional


def build_contextualized_text(
    segment_text: str,
    *,
    doc_title: str = "",
    source_type: str = "",
    global_summary: str = "",
    previous_segment: str = "",
    max_prev_chars: int = 300,
    max_summary_chars: int = 400,
    max_title_chars: int = 150,
) -> str:
    """
    Construye un texto enriquecido con contexto para generar un embedding
    de mayor calidad semántica.

    El formato añade prefijos estructurados que el modelo de embeddings
    (voyage-4-nano) utiliza para desambiguar segmentos con vocabulario
    similar pero significado distinto según el contexto.

    Args:
        segment_text: texto del segmento a embeber.
        doc_title: título o nombre del documento (original_filename).
        source_type: tipo de fuente (entrevista, grupo_focal, etc.).
        global_summary: resumen del documento completo (Fase 2.1).
        previous_segment: texto del segmento inmediatamente anterior.
        max_prev_chars: truncar contexto previo a N caracteres.
        max_summary_chars: truncar resumen global a N caracteres.
        max_title_chars: truncar título a N caracteres.

    Returns:
        Texto enriquecido listo para TEI.embed_query() o TEI.embed_documents().
    """
    parts: List[str] = []

    # ── 1. Identidad del documento ────────────────────────
    if doc_title:
        title = doc_title[:max_title_chars]
        parts.append(f"[Documento: {title}]")

    # ── 2. Tipo de fuente (modula la interpretación) ─────
    # "entrevista" sugiere primera persona, "grupo_focal" sugiere interacción
    if source_type:
        parts.append(f"[Fuente: {source_type}]")

    # ── 3. Resumen global (Fase 2.1) ──────────────────────
    # Da contexto de qué trata el documento completo
    if global_summary:
        summary = global_summary[:max_summary_chars]
        parts.append(f"[Contexto del documento: {summary}]")

    # ── 4. Contexto local: qué se dijo justo antes ────────
    # Crítico para entrevistas: el segmento actual puede ser
    # una respuesta a una pregunta implícita en el segmento previo
    if previous_segment:
        prev = previous_segment[:max_prev_chars]
        parts.append(f"[Contexto previo: {prev}]")

    # ── 5. El segmento en sí ──────────────────────────────
    parts.append(segment_text)

    return "\n".join(parts)


def build_contextualized_text_minimal(
    segment_text: str,
    *,
    doc_title: str = "",
    previous_segment: str = "",
) -> str:
    """
    Versión mínima: solo título del documento + contexto previo.
    Útil cuando no hay resumen global ni tipo de fuente.
    """
    return build_contextualized_text(
        segment_text,
        doc_title=doc_title,
        previous_segment=previous_segment,
    )
