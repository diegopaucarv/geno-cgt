"""Quality scorers — evaluacion algoritmica de codigos (sin LLM).

O6 del plan de optimizaciones. Usa regex para validar estilo de codificacion
y TEI embeddings para detectar redundancia. Solo llama al LLM critic cuando
el chequeo algoritmico encuentra problemas que requieren juicio cualitativo.

Reduce ~60% de las llamadas al critic FLASH.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def evaluate_codes_algorithmic(
    codes: list[dict[str, Any]],
    coding_style: str = "gerundio",
) -> dict[str, Any]:
    """Evalua calidad de codigos sin LLM.

    Usa:
    - Regex para validar estilo (gerundio, in-vivo, etc.)
    - Heuristicas para definicion, grounding, propiedades

    Retorna el mismo formato que el critic LLM para compatibilidad.

    Args:
        codes: Lista de codigos con code_name y definition.
        coding_style: Estilo requerido (gerundio, in_vivo, nominalizacion, etc.)

    Returns:
        {"all_valid": bool, "issues": [{code_name, problem, suggestion}]}
    """
    issues: list[dict[str, str]] = []
    all_valid = True

    for code in codes:
        name = code.get("code_name", "").strip()
        definition = code.get("definition", "").strip()

        # 1. Validar estilo de codificacion (regex)
        style_ok = validate_coding_style(name, coding_style)
        if not style_ok:
            all_valid = False
            issues.append(
                {
                    "code_name": name,
                    "problem": "wrong_style",
                    "suggestion": (
                        f"El nombre debe usar estilo '{coding_style}'. "
                        f"Ejemplo correcto: {_suggest_style_example(name, coding_style)}"
                    ),
                }
            )

        # 2. Validar definicion sustancial
        if len(definition) < 50:
            all_valid = False
            issues.append(
                {
                    "code_name": name,
                    "problem": "vague_definition",
                    "suggestion": (
                        "La definicion debe tener al menos 50 caracteres "
                        "describiendo propiedades y dimensiones."
                    ),
                }
            )

        # 3. Verificar propiedades (detectar definiciones que solo repiten el nombre)
        name_words = set(name.lower().split())
        def_words = set(definition.lower().split())
        overlap = len(name_words & def_words) / max(len(name_words), 1)
        if overlap > 0.8 and len(definition) < 100:
            all_valid = False
            issues.append(
                {
                    "code_name": name,
                    "problem": "missing_properties",
                    "suggestion": (
                        "La definicion solo repite el nombre del codigo. "
                        "Describe que patron de comportamiento captura, "
                        "sus propiedades y como varia."
                    ),
                }
            )

    return {"all_valid": all_valid, "issues": issues}


def validate_coding_style(name: str, style: str) -> bool:
    """Validacion por regex del estilo de codificacion, sin LLM."""
    if style == "gerundio":
        return bool(re.search(r"(ando|iendo)$", name, re.IGNORECASE))
    if style == "in_vivo":
        return name.startswith('"') and name.endswith('"')
    if style == "nominalizacion":
        return bool(
            re.search(r"(cion|miento|dad|encia|anza|ismo|ura)$", name, re.IGNORECASE)
        )
    # Otros estilos sin validacion estricta
    return True


def _suggest_style_example(name: str, style: str) -> str:
    """Sugiere como corregir el nombre segun el estilo requerido."""
    if style == "gerundio":
        # Intentar convertir a gerundio
        if name.endswith("ar"):
            return name[:-2] + "ando"
        if name.endswith("er") or name.endswith("ir"):
            return name[:-2] + "iendo"
        return name + " (convertir a gerundio: -ando/-iendo)"
    if style == "in_vivo":
        return f'"{name}" (usar cita textual del entrevistado)'
    return name


def compare_codes_for_redundancy(
    codes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Detecta pares de codigos redundantes via TEI embeddings.

    Compara todos los pares (O(n^2)) usando cosine similarity.
    Solo retorna los que superan el threshold de 0.85.

    Returns:
        Lista de issues de redundancia en formato critic-compatible.
    """
    from app.core.tei_client import TEIClient

    tei = TEIClient()
    issues: list[dict[str, str]] = []

    if len(codes) < 2:
        return issues

    # Generar embeddings para todos los codigos
    texts = [f"{c.get('code_name', '')}: {c.get('definition', '')}" for c in codes]

    try:
        embeddings = tei.embed_documents_sync(texts)
    except Exception as e:
        logger.warning("Redundancy check skipped (TEI unavailable): %s", e)
        return issues

    # Comparar pares
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            dot = sum(a * b for a, b in zip(embeddings[i], embeddings[j]))
            if dot > 0.85:
                issues.append(
                    {
                        "code_name": codes[i].get("code_name", ""),
                        "problem": "redundant",
                        "suggestion": (
                            f"Similar a '{codes[j].get('code_name', '')}' "
                            f"(similitud: {dot:.2f}). Considerar fusionar ambos codigos."
                        ),
                    }
                )

    return issues
