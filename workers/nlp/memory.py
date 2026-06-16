"""
Memory detection — lee /proc/meminfo y cgroups para saber cuánta RAM
hay DISPONIBLE EN ESTE MOMENTO.

Usado por el segmentador para decidir si cargar vectores, NER, coref, etc.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def available_memory_bytes() -> int:
    """RAM disponible AHORA (bytes). Prioriza cgroup v2 (Docker), fallback a host."""
    # ── Cgroup v2 (Docker con mem_limit) ──
    try:
        with open("/sys/fs/cgroup/memory.current") as f:
            current = int(f.read().strip())
        with open("/sys/fs/cgroup/memory.max") as f:
            raw = f.read().strip()
        if raw != "max":
            limit = int(raw)
            avail = limit - current
            if avail > 0:
                return avail
    except (FileNotFoundError, ValueError, OSError):
        pass

    # ── Cgroup v1 fallback ──
    try:
        with open("/sys/fs/cgroup/memory/memory.usage_in_bytes") as f:
            current = int(f.read().strip())
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            limit = int(f.read().strip())
        # limit can be huge (near MAX_INT) if no limit set
        if limit < (1 << 50):  # reasonable limit (< 1 PB)
            avail = limit - current
            if avail > 0:
                return avail
    except (FileNotFoundError, ValueError, OSError):
        pass

    # ── Host /proc/meminfo ──
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024  # kB → bytes
    except (FileNotFoundError, ValueError, OSError):
        pass

    # ── Last resort ──
    logger.warning("No se pudo detectar memoria disponible. Asumiendo 4 GB.")
    return 4 * 1024**3


def available_memory_gb() -> float:
    return available_memory_bytes() / (1024**3)


# ═══════════════════════════════════════════════════════════════════════
# Auto-config tiers — de más generoso a más restrictivo
# ═══════════════════════════════════════════════════════════════════════


def auto_spacy_exclude(
    min_available_gb: float | None = None,
    spacy_model: str = "es_core_news_lg",
) -> list[str]:
    """Devuelve lista de componentes spaCy a excluir según RAM disponible.

    IMPORTANTE: modelos 'lg' usan StaticVectors en tok2vec.
    Excluir 'vectors' rompe el pipeline. Solo se excluye en 'md' o 'sm'.
    """
    gb = min_available_gb if min_available_gb is not None else available_memory_gb()
    is_lg = spacy_model.endswith("_lg")

    if gb >= 8:
        return []  # todo incluido
    elif gb >= 5:
        return ["lemmatizer"]  # mantiene vectors+tok2vec para lg
    elif gb >= 3:
        if is_lg:
            return ["lemmatizer", "ner"]  # lg sin NER, pero con vectors
        return ["vectors", "lemmatizer"]  # md/sm sin vectors
    else:
        if is_lg:
            return ["lemmatizer", "ner"]  # mínimo funcional para lg
        return ["vectors", "lemmatizer", "ner"]


def should_enable_coref(min_available_gb: float | None = None) -> bool:
    """¿Hay suficiente RAM para cargar Stanza (XLM-RoBERTa)? (~2 GB)."""
    gb = min_available_gb if min_available_gb is not None else available_memory_gb()
    return gb >= 5  # necesita ~2GB libres para Stanza


def auto_concurrency(min_available_gb: float | None = None) -> int:
    """Número de workers según RAM disponible."""
    gb = min_available_gb if min_available_gb is not None else available_memory_gb()
    if gb >= 12:
        return 3
    elif gb >= 8:
        return 2
    elif gb >= 4:
        return 1
    else:
        return 1
