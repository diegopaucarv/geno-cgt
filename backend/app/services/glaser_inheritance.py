"""Herencia de etiquetas Glaser del texto a los segmentos.

Por qué existe
--------------
El pipeline es **classify-first**: el clasificador etiqueta el TEXTO completo y
guarda `metadatos.glaser_blocks` (bloques con su categoría y su rango de
caracteres). La segmentación viene después y debe repartir esa etiqueta entre
los segmentos que produce.

El problema es que el texto de un segmento NO siempre es una subcadena literal
del documento original: `ProgressiveSegmenter` fusiona oraciones por
correferencia, colapsa espacios y normaliza comillas antes de segmentar. Por eso
la búsqueda se hace sobre una versión **normalizada** de ambos lados y, cuando
el mapeo de vuelta al offset original no es fiable, se cae a "el bloque cuyo
texto normalizado contiene el del segmento".

Regla de oro: si no se puede decidir, el tag es ``None``. **Nunca** se inventa
`baseline_data`: un segmento sin etiqueta debe seguir siendo visible para el
detector de inconsistencias, y no debe colarse en la extracción de incidentes.

Este módulo es deliberadamente stdlib-only (no importa SQLAlchemy ni
`workers/`), porque lo cargan tanto `worker-nlp` (que monta
`./backend:/app/backend`) como `worker-heavy`, vía el mismo
`PYTHONPATH=/app/backend:/app/backend/app`.
"""

from __future__ import annotations

import unicodedata

#: Sustituciones carácter-a-carácter de signos tipográficos por ASCII.
#: Las comillas dobles (tipográficas Y ASCII) se pasan a comilla simple porque
#: `preprocess_text` hace `text.replace('"', "'")`: el segmento llega con
#: comillas simples y el texto original con dobles, así que sin esta
#: equivalencia la búsqueda fallaría en cualquier cita.
_TYPOGRAPHIC_MAP = str.maketrans(
    {
        "\u2018": "'",  # ‘
        "\u2019": "'",  # ’
        "\u201a": "'",  # ‚
        "\u201b": "'",  # ‛
        "\u201c": "'",  # “
        "\u201d": "'",  # ”
        "\u201e": "'",  # „
        "\u00ab": "'",  # «
        "\u00bb": "'",  # »
        "\u2032": "'",  # ′
        "\u2033": "'",  # ″
        '"': "'",
        "`": "'",
        "\u2010": "-",  # ‐
        "\u2011": "-",  # ‑
        "\u2012": "-",  # ‒
        "\u2013": "-",  # –
        "\u2014": "-",  # —
        "\u2015": "-",  # ―
        "\u2212": "-",  # −
    }
)

#: Caracteres de anchura cero que `preprocess_text` elimina del texto.
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\ufeff")


def _normalize_tracked(text: str) -> tuple[str, list[int]]:
    """Normaliza ``text`` y devuelve, por cada carácter de salida, su offset.

    El resultado es ``(normalizado, offsets)`` con
    ``offsets[i]`` = índice en ``text`` del carácter original que produjo el
    carácter ``i`` del texto normalizado. Como la normalización puede expandir
    (NFKC), colapsar (espacios) o eliminar (anchura cero), los offsets NO son
    uno-a-uno: por eso `inherit_tags` no puede usar `str.find` sobre el original.

    Se construye en una pasada para que `normalize_for_match` y el mapeo de
    offsets sean SIEMPRE la misma transformación (si divergieran, los tags se
    asignarían al bloque equivocado de forma silenciosa).
    """
    out: list[str] = []
    offsets: list[int] = []
    pending_space = False
    pending_offset = 0

    for index, char in enumerate(text or ""):
        if char in _ZERO_WIDTH:
            continue
        mapped = char.translate(_TYPOGRAPHIC_MAP)
        if mapped.isspace():
            # Colapsa cualquier racha de espacios en uno solo; el offset del
            # espacio es el del primer carácter de la racha.
            if out and not pending_space:
                pending_space = True
                pending_offset = index
            continue
        if pending_space:
            out.append(" ")
            offsets.append(pending_offset)
            pending_space = False
        for piece in unicodedata.normalize("NFKC", mapped):
            if piece.isspace():
                if out:
                    pending_space = True
                    pending_offset = index
                continue
            out.append(piece)
            offsets.append(index)

    return "".join(out), offsets


def normalize_for_match(text: str) -> str:
    """Normaliza ``text`` para comparar segmentos con bloques y con el original.

    Réplica deliberadamente cercana de
    ``ProgressiveSegmenter.preprocess_text`` (``workers/nlp/segmentador.py``):
    NFKC, comillas/dashes tipográficos a ASCII, eliminación de caracteres de
    anchura cero, colapso de espacios y ``strip()``. No necesita ser idéntica
    al segmentador — sólo lo bastante parecida para que el texto de un segmento
    se encuentre dentro del texto normalizado del documento.
    """
    return _normalize_tracked(text)[0]


def blocks_from_metadatos(meta: dict | None) -> list[dict]:
    """Extrae los bloques de clasificación de ``documentos.metadatos``.

    Descarta lo que no tenga forma de bloque (`class` + `text`) para que los
    metadatos escritos por versiones anteriores no rompan la herencia. No
    normaliza la categoría: se copia tal cual y el consumidor decide si es
    canónica.
    """
    if not isinstance(meta, dict):
        return []
    raw_blocks = meta.get("glaser_blocks")
    if not isinstance(raw_blocks, list):
        return []

    blocks: list[dict] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        clase = block.get("class")
        text = block.get("text")
        if not isinstance(clase, str) or not isinstance(text, str):
            continue
        blocks.append(
            {
                "class": clase,
                "text": text,
                "start_char": block.get("start_char"),
                "end_char": block.get("end_char"),
            }
        )
    return blocks


def _find_block_by_offset(prepared: list[dict], offset: int) -> dict | None:
    """Primer bloque cuyo ``[start_char, end_char)`` contiene ``offset``."""
    for block in prepared:
        start = block.get("start_char")
        end = block.get("end_char")
        if start is None or end is None:
            continue
        if start <= offset < end:
            return block
    return None


def _find_block_by_text(
    prepared: list[dict], needle: str, from_index: int
) -> dict | None:
    """Primer bloque (en orden) cuyo texto normalizado contiene ``needle``.

    Busca hacia adelante desde ``from_index``: retroceder asignaría a un
    segmento del final del documento un tag del principio y propagaría el error
    al resto de la corrida.
    """
    if not needle:
        return None
    for block in prepared[from_index:]:
        if needle in block["norm"]:
            return block
    return None


def inherit_tags(
    segment_texts: list[str], blocks: list[dict], full_text: str
) -> list[str | None]:
    """Asigna a cada segmento la categoría del bloque del que proviene.

    Algoritmo de cursor ordenado:

    1. Se normaliza ``full_text`` guardando el offset original de cada carácter.
    2. Para cada segmento (en orden) se toma ``needle`` = primeros 80 caracteres
       del texto normalizado y se busca hacia adelante desde ``cursor``.
    3. Si se encuentra, el offset original se lee del mapa y se devuelve el
       bloque que lo contiene.
    4. Si el match o el mapeo no son fiables, se busca el bloque (en orden) cuyo
       texto normalizado contiene ``needle``.
    5. Si nada encaja, el tag es ``None`` — nunca `baseline_data`.

    Returns:
        Una lista del mismo largo y orden que ``segment_texts``.
    """
    prepared: list[dict] = []
    for index, block in enumerate(blocks or []):
        if not isinstance(block, dict):
            continue
        prepared.append(
            {
                "index": index,
                "class": block.get("class"),
                "norm": normalize_for_match(block.get("text") or ""),
                "start_char": block.get("start_char"),
                "end_char": block.get("end_char"),
            }
        )

    norm_full, offsets = _normalize_tracked(full_text or "")

    tags: list[str | None] = []
    cursor = 0
    block_cursor = 0

    for text in segment_texts or []:
        needle = normalize_for_match(text or "")[:80]
        tag: str | None = None

        if needle:
            abs_idx = norm_full.find(needle, cursor)
            block = None
            if abs_idx >= 0:
                original_offset = offsets[abs_idx] if abs_idx < len(offsets) else None
                if original_offset is not None:
                    block = _find_block_by_offset(prepared, original_offset)
                # Avanzar el cursor aunque el mapeo falle: la posición sí se
                # encontró y los siguientes segmentos van más adelante.
                cursor = abs_idx + len(needle)
                if block is not None:
                    block_cursor = max(block_cursor, block["index"])

            if block is None:
                located = _find_block_by_text(prepared, needle, block_cursor)
                if located is not None:
                    block = located
                    block_cursor = located["index"]

            if block is not None:
                tag = block.get("class")

        tags.append(tag)

    return tags
