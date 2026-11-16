"""Clasificación Glaser para worker-heavy.

Camino canónico (**classify-first**):

- `classify_text_spans` — etiqueta el TEXTO completo en las 5 categorías y
  persiste `glaser_blocks` / `texto_clasificado` / `baseline_tags` **sin crear
  segmentos**. Es el punto de entrada del pipeline: `crudo|preprocesado` →
  `clasificando` → `clasificado`.
- La segmentación posterior (`workers/nlp/tasks.py::segmentar_documento`) crea
  los segmentos y hereda el tag del tramo de origen (`tipo_dato_glaser`), de
  modo que la clasificación sigue viva aunque los segmentos cambien.

Camino legacy (todavía soportado por `classify_document`):

1. **Hay segmentadores** (`workers/nlp`): los segmentos ya existen en la BD.
   Se clasifica **cada segmento** con `fa_segment_classifier` y después se
   **fusionan** los segmentos contiguos que comparten categoría. Dos tramos de
   la misma categoría separados por otra categoría NO se fusionan:
   `1 baseline, 2 baseline, 3 otra, 4 baseline` produce tres bloques:
   `1-2 baseline`, `3 otra`, `4 baseline`.

2. **No hay segmentadores**: el LLM hace ambas cosas en una sola pasada con
   `fa_segment_and_classify` (divide el texto y clasifica cada trozo). Los
   segmentos creados así no tienen `embedding`, lo cual degrada la búsqueda
   híbrida pero mantiene el pipeline en marcha.

`glaser_classifier.py` NO se toca: sigue siendo el camino legacy con tags XML,
con sus internos pinneados por `tests/workflow/test_classification_wiring.py`.

Persistencia (sin migración de esquema):

- `segmentos.tipo_dato_glaser` — categoría canónica por segmento.
- `documentos.metadatos.glaser_blocks` — bloques fusionados (JSONB).
- `documentos.metadatos.texto_clasificado` — vista XML derivada, para no romper
  el renderer legacy mientras el frontend migra a los bloques.
- `documentos.metadatos.glaser_used_fallback` — True si se usó el camino (2).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Taxonomía canónica (5 categorías — las que existen en la BD)
# ═══════════════════════════════════════════════════════════════════════

CLASSES_GLASER: tuple[str, ...] = (
    "baseline_data",
    "properline_data",
    "interpreted_data",
    "vague_data",
    "document_context",
)

#: Categoría de reserva cuando el LLM no devuelve nada para un segmento.
#: Es `baseline_data` a propósito: ante la duda se conserva el dato para la
#: extracción de incidentes, igual que hacía el fallback legacy (marcar todo el
#: documento como baseline). Un fallo SISTEMÁTICO no cae aquí: se degrada.
DEFAULT_CLASS = "baseline_data"

#: Alias aceptados (incluye los tags legacy processual_data / contextual_data).
_ALIASES: dict[str, str] = {
    "baseline": "baseline_data",
    "baseline data": "baseline_data",
    "baselinedata": "baseline_data",
    "baseline_data": "baseline_data",
    "properline": "properline_data",
    "proper line": "properline_data",
    "proper_line": "properline_data",
    "proper_line_data": "properline_data",
    "properlinedata": "properline_data",
    "properline_data": "properline_data",
    "interpreted": "interpreted_data",
    "interpreted data": "interpreted_data",
    "interpretative": "interpreted_data",
    "interpreted_data": "interpreted_data",
    "vague": "vague_data",
    "vague data": "vague_data",
    "vague_data": "vague_data",
    "document": "document_context",
    "document context": "document_context",
    "document_context": "document_context",
    "structure": "document_context",
    # Alias legacy: la categoría se llamaba `interviewer_context` y significaba
    # lo mismo (estructura del documento: preguntas del investigador, títulos,
    # metadatos). Las filas antiguas se normalizan sin gastar LLM.
    "interviewer": "document_context",
    "interviewer context": "document_context",
    "interviewer_context": "document_context",
    "context": "document_context",
    # Tags del clasificador legacy, normalizados a la taxonomía canónica.
    # `contextual_data` cubría "introducciones, transiciones y pasajes que no
    # expresan contenido sustantivo": su equivalente canónico es vague_data
    # (describir el entorno no es dato de línea base ni norma social, y no debe
    # inflar el baseline que alimenta la extracción de incidentes).
    "contextual_data": "vague_data",
    "processual_data": "baseline_data",
}

#: Prefijos que delatan estructura del documento (no sustancia): quien pregunta
#: en una transcripción, un encabezado Markdown, o un rótulo de sección.
_STRUCTURE_PREFIX = re.compile(
    r"^\s*(?:"
    r"#{1,6}\s+"  # encabezado Markdown
    r"|(?:\(?\s*)?(?:"
    r"interviewer|entrevistador(?:a)?|moderador(?:a)?|facilitador(?:a)?|"
    r"investigador(?:a)?|researcher|question|pregunta|q|i|e|m|facilitator"
    r")\s*(?:\)?\s*)?[:.\-–—]"
    r"|(?:section|sección|seccion|capítulo|capitulo|chapter|parte|part|apartado|anexo|annex|apéndice|apendice|appendix)"
    r"\s*(?:\d+\b|[:.\-–—])"
    r")",
    re.IGNORECASE,
)

#: Ventana máxima de una llamada al LLM en el camino fallback.
FALLBACK_WINDOW_CHARS = 12000
#: Segmentos máximos por llamada en el camino principal.
MAX_SEGMENTS_PER_CALL = 40
#: Caracteres máximos de segmentos por llamada en el camino principal.
MAX_SEGMENTS_CHARS_PER_CALL = 12000


# ═══════════════════════════════════════════════════════════════════════
# Normalización
# ═══════════════════════════════════════════════════════════════════════


def _normalizar_clase(raw: Any) -> str:
    """Devuelve una categoría canónica a partir de cualquier etiqueta del LLM.

    Tolera mayúsculas, espacios, guiones, prefijos como ``<baseline_data>`` y
    los tags legacy ``processual_data`` / ``contextual_data``. Si no reconoce
    nada, devuelve `DEFAULT_CLASS` en lugar de propagar una categoría inválida.
    """
    if not isinstance(raw, str):
        return DEFAULT_CLASS

    key = raw.strip().strip("<>/").strip().lower()
    key = re.sub(r"[\s\-]+", "_", key)
    key = re.sub(r"[^a-z0-9_]", "", key)

    if not key:
        return DEFAULT_CLASS
    if key in CLASSES_GLASER:
        return key
    if key in _ALIASES:
        return _ALIASES[key]

    # Último recurso: cualquier etiqueta que *contenga* una categoría.
    for cls in CLASSES_GLASER:
        stem = cls.replace("_data", "").replace("_context", "")
        if stem and stem in key:
            return cls
    return DEFAULT_CLASS


def _normalizar_confianza(raw: Any) -> str:
    value = str(raw or "").strip().upper()
    return value if value in ("HIGH", "MEDIUM", "LOW") else "MEDIUM"


#: Rango de confianza para fusionar bloques: el bloque vale lo que su segmento
#: más débil, nunca más.
_CONFIDENCE_RANK: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _parse_segment_id(raw: Any) -> int | None:
    """Extrae el número de segmento de lo que devuelva el LLM."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    match = re.search(r"-?\d+", str(raw or ""))
    return int(match.group(0)) if match else None


def _prior_algoritmico(texto: str) -> str:
    """Categoría de reserva para un segmento que el LLM no clasificó.

    Deliberadamente conservador: solo reconoce estructura explícita del documento
    (prefijo de hablante, encabezado o rótulo de sección) y el resto cae a
    `DEFAULT_CLASS`. No pretende sustituir al LLM, solo evitar que un segmento
    quede sin `tipo_dato_glaser`.
    """
    body = (texto or "").strip()
    if not body:
        return DEFAULT_CLASS
    if _STRUCTURE_PREFIX.match(body):
        return "document_context"
    return DEFAULT_CLASS


# ═══════════════════════════════════════════════════════════════════════
# Troceado
# ═══════════════════════════════════════════════════════════════════════


def _chunks(
    items: list[dict],
    max_items: int = MAX_SEGMENTS_PER_CALL,
    max_chars: int = MAX_SEGMENTS_CHARS_PER_CALL,
) -> list[list[dict]]:
    """Agrupa segmentos en lotes acotados por número y por tamaño."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    chars = 0
    for item in items:
        size = len(item.get("text") or "")
        if current and (len(current) >= max_items or chars + size > max_chars):
            batches.append(current)
            current = []
            chars = 0
        current.append(item)
        chars += size
    if current:
        batches.append(current)
    return batches


def _windows(raw_text: str, max_chars: int = FALLBACK_WINDOW_CHARS) -> list[str]:
    """Parte el texto en ventanas que cortan preferentemente en párrafos."""
    if not raw_text:
        return []
    if len(raw_text) <= max_chars:
        return [raw_text]

    windows: list[str] = []
    current = ""
    for part in re.split(r"(\n\s*\n)", raw_text):
        if current and len(current) + len(part) > max_chars:
            windows.append(current)
            current = ""
        current += part
    if current:
        windows.append(current)

    # Ventanas que siguen siendo enormes (un único párrafo gigante) se cortan
    # por carácter; el corte puede caer a mitad de palabra y es aceptable,
    # porque el LLM devuelve subcadenas del texto que recibe.
    bounded: list[str] = []
    for window in windows:
        rest = window
        while len(rest) > max_chars:
            cut = rest.rfind("\n", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            bounded.append(rest[:cut])
            rest = rest[cut:]
        if rest:
            bounded.append(rest)
    return bounded or [raw_text]


# ═══════════════════════════════════════════════════════════════════════
# Camino 1: clasificar segmentos existentes
# ═══════════════════════════════════════════════════════════════════════


def _render_batch(batch: list[dict]) -> str:
    """Renderiza el lote con ordinales LOCALES, siempre 1..N.

    Cada llamada recibe una lista que empieza en 1, así que el modelo no puede
    renumerar y perder el lote entero; `_call_classifier` traduce ese ordinal de
    vuelta a la `position` global del documento.
    """
    return "\n\n".join(
        f"{index}. {item['text']}" for index, item in enumerate(batch, start=1)
    )


def _call_classifier(
    batch: list[dict],
    proyecto_id: str,
    llm_client,
    temperature: float = 0.1,
) -> dict[int, dict]:
    """Una llamada a `fa_segment_classifier` para un lote de segmentos."""
    out = llm_client.run_agent(
        agent_id="fa_segment_classifier",
        variables={
            "segments_batch": "",
            "proyecto_id": proyecto_id,
            "project_id": proyecto_id,
        },
        # El lote va en el mensaje del usuario: el prefijo (instrucciones +
        # schema) queda idéntico entre documentos y por tanto cacheable.
        # `tail_variables` solo actúa si la plantilla contiene el placeholder;
        # hoy no lo contiene y se mantiene como red de seguridad.
        tail_variables=("segments_batch",),
        user_content=_render_batch(batch),
        cache_key=str(proyecto_id) if proyecto_id else None,
        # Sin max_tokens: el presupuesto lo fija el tier (MODEL_FLASH_MAX_TOKENS /
        # MODEL_PRO_MAX_TOKENS, ajustable desde ⚙) y se hereda en run_agent.
        # Los lotes están acotados a MAX_SEGMENTS_PER_CALL segmentos y
        # MAX_SEGMENTS_CHARS_PER_CALL caracteres, así que caben de sobra.
        temperature=temperature,
    )

    if not out.success:
        raise RuntimeError(out.error or "fa_segment_classifier falló sin detalle")

    payload = out.data or {}
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))

    raw_items = payload.get("classifications")
    if not isinstance(raw_items, list):
        raise RuntimeError("fa_segment_classifier no devolvió 'classifications'")

    # El lote se numera 1..N en cada llamada. Si el modelo devuelve posiciones
    # globales del documento (fuera de ese rango) también se aceptan.
    ordinal = {index: item["position"] for index, item in enumerate(batch, start=1)}
    global_positions = set(ordinal.values())

    resolved: dict[int, dict] = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        parsed = _parse_segment_id(entry.get("segment_id"))
        if parsed is None:
            parsed = _parse_segment_id(entry.get("position"))
        if parsed is None:
            continue
        position = ordinal.get(parsed)
        if position is None and parsed in global_positions:
            position = parsed
        if position is None:
            continue
        resolved[position] = {
            "position": position,
            "category": _normalizar_clase(
                entry.get("category") or entry.get("glaser_data_type")
            ),
            "confidence": _normalizar_confianza(entry.get("confidence")),
        }

    if not resolved:
        # Un lote sin ninguna posición reconocible es un lote fallido, no un
        # lote "ok": el llamador decide si reintentar o degradar.
        raise RuntimeError(
            "fa_segment_classifier devolvió 0 clasificaciones utilizables "
            f"de {len(batch)} segmentos"
        )
    return resolved


def classify_segments_json_schema(
    segmentos: list[dict],
    proyecto_id: str,
    llm_client,
) -> list[dict]:
    """Clasifica cada segmento con JSON Schema.

    Args:
        segmentos: ``[{"position": int, "text": str}, ...]``.
        proyecto_id: usado como afinidad de caché y contexto.
        llm_client: cliente de worker-heavy (``agents.LLMClient``).

    Returns:
        ``[{"position": int, "category": str, "confidence": str}, ...]`` en el
        mismo orden que ``segmentos``.

    Raises:
        RuntimeError: si todas las llamadas fallan (el llamador degrada).
    """
    if not segmentos:
        return []

    ordered = sorted(segmentos, key=lambda item: item["position"])
    result: dict[int, dict] = {}
    failures: list[str] = []
    ok_batches = 0
    prior_filled = 0

    for batch in _chunks(ordered):
        try:
            result.update(_call_classifier(batch, proyecto_id, llm_client))
            ok_batches += 1
        except Exception as exc:  # noqa: BLE001 - se agrega y se decide abajo
            logger.warning(
                "fa_segment_classifier falló para %d segmentos: %s",
                len(batch),
                exc,
            )
            failures.append(str(exc))
            continue

        missing = [item for item in batch if item["position"] not in result]
        if missing:
            # Una segunda pasada a temperatura 0 suele recuperar las posiciones
            # que el modelo omitió; si vuelve a faltar alguna, el prior decide.
            logger.info(
                "fa_segment_classifier omitió %d/%d segmentos; reintentando",
                len(missing),
                len(batch),
            )
            try:
                result.update(
                    _call_classifier(missing, proyecto_id, llm_client, temperature=0.0)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reintento de clasificación falló: %s", exc)

            for item in missing:
                if item["position"] not in result:
                    result[item["position"]] = {
                        "position": item["position"],
                        "category": _prior_algoritmico(item.get("text") or ""),
                        "confidence": "LOW",
                    }
                    prior_filled += 1

    # Un fallo sistemático (ningún lote respondió) es degradación, no un
    # documento clasificado con el prior puesto a todo.
    if failures and ok_batches == 0:
        raise RuntimeError(
            "clasificación por segmentos no disponible: " + "; ".join(failures[:3])
        )
    if failures or prior_filled:
        # Fallo parcial: hay resultado, pero no es fruto solo del modelo. Se
        # registra a nivel error para que sea visible en los logs.
        logger.error(
            "fa_segment_classifier parcial: %d/%d lotes fallaron, %d segmentos "
            "quedaron con el prior (%s)",
            len(failures),
            ok_batches + len(failures),
            prior_filled,
            DEFAULT_CLASS,
        )

    out: list[dict] = []
    for item in ordered:
        out.append(
            result.get(
                item["position"],
                {
                    "position": item["position"],
                    "category": _prior_algoritmico(item.get("text") or ""),
                    "confidence": "LOW",
                },
            )
        )
    return out


# ═══════════════════════════════════════════════════════════════════════
# Fusión por contigüidad
# ═══════════════════════════════════════════════════════════════════════


def merge_adjacent_segments(
    clasificaciones: list[dict],
    textos: dict[int, str],
) -> list[dict]:
    """Fusiona segmentos consecutivos que comparten categoría.

    La fusión es estrictamente por contigüidad: ``posicion == anterior + 1``.
    Un segmento de otra categoría corta el bloque, de modo que la misma
    categoría puede aparecer en varios bloques.

    Returns:
        ``[{"class", "start_pos", "end_pos", "segment_positions",
        "confidence", "text"}, ...]``
    """
    blocks: list[dict] = []
    current: dict | None = None

    for entry in sorted(clasificaciones, key=lambda item: item["position"]):
        position = entry["position"]
        category = _normalizar_clase(entry.get("category"))
        confidence = _normalizar_confianza(entry.get("confidence"))
        piece = (textos.get(position) or "").strip()

        contiguous = (
            current is not None
            and category == current["class"]
            and position == current["end_pos"] + 1
        )
        if contiguous:
            current["end_pos"] = position
            current["segment_positions"].append(position)
            if piece:
                current["text"] = (
                    f"{current['text']} {piece}".strip() if current["text"] else piece
                )
            if _CONFIDENCE_RANK[confidence] < _CONFIDENCE_RANK[current["confidence"]]:
                # El bloque hereda la confianza de su segmento más débil.
                current["confidence"] = confidence
            continue

        current = {
            "class": category,
            "start_pos": position,
            "end_pos": position,
            "segment_positions": [position],
            "confidence": confidence,
            "text": piece,
        }
        blocks.append(current)

    return blocks


def blocks_to_xml(blocks: list[dict]) -> str:
    """Deriva la vista XML clasificada a partir de los bloques fusionados."""
    parts: list[str] = []
    for block in blocks:
        body = (block.get("text") or "").strip()
        if not body:
            continue
        tag = _normalizar_clase(block.get("class"))
        # Tags reales (no comentarios): es el formato que renderiza el frontend.
        parts.append(f"<{tag}>{body}</{tag}>")
    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# Camino 2: el LLM segmenta y clasifica (fallback)
# ═══════════════════════════════════════════════════════════════════════


def _locate_offsets(raw_text: str, items: list[dict]) -> list[dict]:
    """Rellena `start_char` / `end_char` / `is_exact_match` buscando en el original."""
    cursor = 0
    for item in items:
        body = (item.get("text") or "").strip()
        if not body:
            item["start_char"] = None
            item["end_char"] = None
            item["is_exact_match"] = False
            continue
        start = raw_text.find(body, cursor)
        if start < 0:
            # El modelo pudo devolver el fragmento desordenado; se acepta, pero
            # no se rebobina el cursor para no romper el anclaje.
            start = raw_text.find(body)
        if start >= 0:
            item["start_char"] = start
            item["end_char"] = start + len(body)
            item["is_exact_match"] = True
            cursor = max(cursor, item["end_char"])
        else:
            item["start_char"] = None
            item["end_char"] = None
            item["is_exact_match"] = False
    return items


def _call_segment_and_classify(
    window: str,
    proyecto_id: str,
    llm_client,
    temperature: float = 0.1,
) -> list[dict]:
    out = llm_client.run_agent(
        agent_id="fa_segment_and_classify",
        variables={
            "raw_text": "",
            "proyecto_id": proyecto_id,
            "project_id": proyecto_id,
        },
        tail_variables=("raw_text",),
        user_content=window,
        cache_key=str(proyecto_id) if proyecto_id else None,
        # Sin max_tokens: el presupuesto lo fija el tier (ajustable desde ⚙) y
        # se hereda en run_agent. La ventana está acotada a FALLBACK_WINDOW_CHARS.
        temperature=temperature,
    )

    if not out.success:
        raise RuntimeError(out.error or "fa_segment_and_classify falló sin detalle")
    payload = out.data or {}
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))

    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise RuntimeError("fa_segment_and_classify no devolvió 'segments'")

    items: list[dict] = []
    for entry in raw_segments:
        if not isinstance(entry, dict):
            continue
        body = entry.get("text")
        if not isinstance(body, str) or not body.strip():
            continue
        # Se guarda exactamente lo que se ancla en el original (sin espacios en
        # los extremos), para que start_char/end_char sigan siendo válidos.
        body = body.strip()
        items.append(
            {
                "text": body,
                "category": _normalizar_clase(entry.get("category")),
                "confidence": _normalizar_confianza(entry.get("confidence")),
            }
        )
    if not items:
        raise RuntimeError("fa_segment_and_classify devolvió segmentos vacíos")
    return items


def llm_segment_and_classify(
    raw_text: str,
    proyecto_id: str,
    llm_client,
) -> list[dict]:
    """Divide el texto y clasifica cada trozo en una sola pasada.

    Returns:
        ``[{"position", "text", "category", "confidence", "start_char",
        "end_char", "is_exact_match"}, ...]`` con posiciones globales 1..N.
    """
    if not (raw_text or "").strip():
        return []

    collected: list[dict] = []
    failures: list[str] = []
    for window in _windows(raw_text):
        if not window.strip():
            continue
        try:
            collected.extend(
                _call_segment_and_classify(window, proyecto_id, llm_client)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ventana de %d chars no clasificada: %s", len(window), exc)
            failures.append(str(exc))

    if not collected:
        return []
    if failures:
        # Persistir sólo una parte del documento lo dejaría truncado y, al haber
        # segmentos, el siguiente intento tomaría el camino 1 sobre esos
        # segmentos incompletos. Mejor degradar y permitir el reintento.
        raise RuntimeError(
            "segmentación por LLM incompleta: "
            f"{len(failures)} ventana(s) fallaron; " + "; ".join(failures[:3])
        )

    located = _locate_offsets(raw_text, collected)
    # Orden estable: por offset en el original. Los fragmentos que no se pudieron
    # anclar se intercalan justo después del último anclado, en lugar de saltar
    # al final del documento.
    keyed: list[tuple[float, int, dict]] = []
    key = -1.0
    for index, item in enumerate(located):
        if item["start_char"] is not None:
            key = float(item["start_char"])
        else:
            key += 0.5
        keyed.append((key, index, item))
    keyed.sort(key=lambda row: (row[0], row[1]))

    out: list[dict] = []
    for position, (_, _, item) in enumerate(keyed, start=1):
        out.append(
            {
                "position": position,
                "text": item["text"].strip(),
                "category": item["category"],
                "confidence": item["confidence"],
                "start_char": item["start_char"],
                "end_char": item["end_char"],
                "is_exact_match": item["is_exact_match"],
            }
        )
    return out


# ═══════════════════════════════════════════════════════════════════════
# Orquestación y persistencia
# ═══════════════════════════════════════════════════════════════════════


def _documento_metadatos(session, documento_id: str) -> dict:
    row = session.execute(
        text("SELECT metadatos FROM documentos WHERE id = :did"),
        {"did": documento_id},
    ).fetchone()
    if not row or row[0] is None:
        return {}
    raw = row[0]
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _raw_text_de(meta: dict) -> str:
    return (
        meta.get("texto_preprocesado")
        or meta.get("texto_extraido")
        or meta.get("texto_original")
        or ""
    ).strip()


def _leer_segmentos(session, documento_id: str) -> list[dict]:
    rows = session.execute(
        text(
            "SELECT id, texto, posicion FROM segmentos "
            "WHERE documento_id = :did ORDER BY posicion"
        ),
        {"did": documento_id},
    ).fetchall()
    return [
        {"id": str(row[0]), "text": row[1] or "", "position": int(row[2] or 0)}
        for row in rows
    ]


def _first_10(texto: str) -> str:
    return " ".join((texto or "").split()[:10])[:200]


def _persistir_segmentos_fallback(
    session, documento_id: str, segments: list[dict]
) -> None:
    """INSERTa los segmentos que creó el LLM. No toca los embeddings."""
    import uuid as _uuid

    session.execute(
        text("DELETE FROM segmentos WHERE documento_id = :did"),
        {"did": documento_id},
    )
    for seg in segments:
        session.execute(
            text(
                "INSERT INTO segmentos "
                "(id, documento_id, texto, posicion, conteo_tokens, "
                " tipo_dato_glaser, first_10, start_char, end_char, "
                " is_exact_match, es_anomalia) "
                "VALUES (:sid, :did, :txt, :pos, :tok, :tipo, :f10, :sc, :ec, :iem, false)"
            ),
            {
                "sid": str(_uuid.uuid4()),
                "did": documento_id,
                "txt": seg["text"],
                "pos": seg["position"],
                "tok": len(seg["text"].split()),
                "tipo": seg["category"],
                "f10": _first_10(seg["text"]),
                "sc": seg.get("start_char"),
                "ec": seg.get("end_char"),
                "iem": bool(seg.get("is_exact_match", True)),
            },
        )


def _persistir_metadatos(session, documento_id: str, patch: dict) -> None:
    session.execute(
        text(
            "UPDATE documentos SET metadatos = "
            "COALESCE(metadatos, '{}'::jsonb) || CAST(:patch AS jsonb) "
            "WHERE id = :did"
        ),
        {"patch": json.dumps(patch, ensure_ascii=False), "did": documento_id},
    )


# ═══════════════════════════════════════════════════════════════════════
# Etiquetas legacy: normalización determinista (sin LLM)
# ═══════════════════════════════════════════════════════════════════════

#: Lista SQL de categorías canónicas, para los guards de idempotencia.
CANONICAL_CLASS_SQL: str = "(" + ", ".join(f"'{c}'" for c in CLASSES_GLASER) + ")"

#: Etiquetas de la taxonomía vieja que pueden sobrevivir dentro de un XML
#: clasificado antiguo.
_LEGACY_TAG_RE = re.compile(
    r"<\s*/?\s*(processual_data|contextual_data|interviewer_context)\b", re.IGNORECASE
)


def contar_segmentos_sin_clasificar(session, documento_id: str) -> tuple[int, int]:
    """Devuelve ``(total, sin_clasificar)`` de los segmentos del documento.

    Cuenta como "sin clasificar" los ``NULL`` **y** cualquier etiqueta fuera de
    la taxonomía canónica. Sin lo segundo, un resto legacy
    (``processual_data`` / ``contextual_data``) cuenta como clasificado para
    siempre y el guard de idempotencia nunca lo normaliza.
    """
    row = session.execute(
        text(
            "SELECT COUNT(*), COUNT(*) FILTER ("
            " WHERE tipo_dato_glaser IS NULL"
            f" OR tipo_dato_glaser NOT IN {CANONICAL_CLASS_SQL}"
            ") FROM segmentos WHERE documento_id = :did"
        ),
        {"did": documento_id},
    ).fetchone()
    if not row:
        return (0, 0)
    return (int(row[0] or 0), int(row[1] or 0))


def _meta_tiene_tags_legacy(meta: dict) -> bool:
    """¿Los metadatos derivados conservan etiquetas fuera de la taxonomía?"""
    for block in meta.get("glaser_blocks") or []:
        if isinstance(block, dict):
            clase = block.get("class")
            if isinstance(clase, str) and _normalizar_clase(clase) != clase:
                return True
    xml = meta.get("texto_clasificado")
    return isinstance(xml, str) and bool(_LEGACY_TAG_RE.search(xml))


def normalizar_etiquetas_legacy(session, documento_id: str) -> dict:
    """Traduce etiquetas legacy a la taxonomía canónica, sin gastar LLM.

    El clasificador nuevo nunca emite ``processual_data`` / ``contextual_data`` /
    ``interviewer_context``, pero las filas clasificadas antes del rediseño los
    conservan. Como no son ``NULL``, el guard de idempotencia las daba por buenas
    y el documento se quedaba con la taxonomía vieja (y con sus segmentos
    excluidos de la extracción de incidentes, que sólo lee ``baseline_data``).

    Aquí se aplican los mismos alias que usa el clasificador
    (``processual_data`` → ``baseline_data``, ``contextual_data`` →
    ``vague_data``, ``interviewer_context`` → ``document_context``) y, si hacía
    falta, se reconstruyen ``glaser_blocks`` /
    ``texto_clasificado`` para que la vista clasificada no muestre tags crudos.

    Returns:
        ``{"changed": int, "rebuilt": bool, "total": int}``.
    """
    rows = session.execute(
        text("SELECT id, tipo_dato_glaser FROM segmentos WHERE documento_id = :did"),
        {"did": documento_id},
    ).fetchall()

    etiquetas: dict[str, str | None] = {}
    changed = 0
    for row in rows:
        seg_id = str(row[0])
        raw = row[1]
        if raw is None:
            etiquetas[seg_id] = None
            continue
        canonica = _normalizar_clase(raw)
        etiquetas[seg_id] = canonica
        if canonica != raw:
            session.execute(
                text("UPDATE segmentos SET tipo_dato_glaser = :tipo WHERE id = :sid"),
                {"tipo": canonica, "sid": seg_id},
            )
            changed += 1

    meta_legacy = _meta_tiene_tags_legacy(_documento_metadatos(session, documento_id))

    rebuilt = False
    # Con algún segmento sin clasificar manda el camino del LLM: reconstruir la
    # vista ahora la dejaría incompleta.
    if (
        (changed or meta_legacy)
        and etiquetas
        and all(etiqueta is not None for etiqueta in etiquetas.values())
    ):
        segmentos = _leer_segmentos(session, documento_id)
        clasificados = [
            {
                "position": seg["position"],
                "category": etiquetas[seg["id"]],
                "confidence": "MEDIUM",
            }
            for seg in segmentos
            if etiquetas.get(seg["id"])
        ]
        if clasificados:
            blocks = merge_adjacent_segments(
                clasificados, {seg["position"]: seg["text"] for seg in segmentos}
            )
            _persistir_metadatos(
                session,
                documento_id,
                {
                    "glaser_blocks": blocks,
                    "texto_clasificado": blocks_to_xml(blocks),
                    "baseline_tags": [
                        block["text"]
                        for block in blocks
                        if block["class"] == "baseline_data"
                    ],
                },
            )
            rebuilt = True

    return {"changed": changed, "rebuilt": rebuilt, "total": len(etiquetas)}


def classify_document(
    documento_id: str,
    proyecto_id: str,
    session,
    llm_client,
) -> dict:
    """Clasifica un documento completo y persiste el resultado.

    Punto de entrada único para `tasks.py`. Decide entre clasificar segmentos
    existentes (camino 1) y segmentar+clasificar con el LLM (camino 2).

    Returns:
        dict con ``status`` (``ok`` | ``degraded``), ``reason``, ``blocks``,
        ``segments``, ``used_fallback``, ``baseline_tags_count`` y
        ``segments_classified``.
    """
    resultado: dict[str, Any] = {
        "status": "ok",
        "reason": None,
        "blocks": [],
        "segments": 0,
        "used_fallback": False,
        "baseline_tags_count": 0,
        "segments_classified": 0,
    }

    meta = _documento_metadatos(session, documento_id)
    existentes = _leer_segmentos(session, documento_id)
    used_fallback = False
    blocks: list[dict] = []
    clasificados: list[dict] = []

    if existentes:
        # ── Camino 1: los segmentos ya existen ──
        try:
            clasificados = classify_segments_json_schema(
                [{"position": s["position"], "text": s["text"]} for s in existentes],
                proyecto_id,
                llm_client,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Clasificación por segmentos no disponible doc=%s: %s",
                documento_id[:8],
                exc,
            )
            resultado["status"] = "degraded"
            resultado["reason"] = f"segment classification failed: {exc}"
            resultado["segments"] = len(existentes)
            resultado["segments_classified"] = 0
            return resultado

        by_position = {seg["position"]: seg["id"] for seg in existentes}
        textos = {seg["position"]: seg["text"] for seg in existentes}
        for entry in clasificados:
            seg_id = by_position.get(entry["position"])
            if not seg_id:
                continue
            session.execute(
                text("UPDATE segmentos SET tipo_dato_glaser = :tipo WHERE id = :sid"),
                {"tipo": entry["category"], "sid": seg_id},
            )
        blocks = merge_adjacent_segments(clasificados, textos)

    else:
        # ── Camino 2: sin segmentadores, el LLM hace las dos cosas ──
        used_fallback = True
        raw_text = _raw_text_de(meta)
        if not raw_text:
            resultado["status"] = "degraded"
            resultado["reason"] = "document has no text to segment"
            resultado["used_fallback"] = True
            return resultado

        try:
            segments = llm_segment_and_classify(raw_text, proyecto_id, llm_client)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Segmentación por LLM no disponible doc=%s: %s",
                documento_id[:8],
                exc,
            )
            resultado["status"] = "degraded"
            resultado["reason"] = f"llm segmentation failed: {exc}"
            resultado["used_fallback"] = True
            return resultado

        if not segments:
            resultado["status"] = "degraded"
            resultado["reason"] = "llm returned no segments"
            resultado["used_fallback"] = True
            return resultado

        _persistir_segmentos_fallback(session, documento_id, segments)
        clasificados = [
            {
                "position": seg["position"],
                "category": seg["category"],
                "confidence": seg["confidence"],
            }
            for seg in segments
        ]
        blocks = merge_adjacent_segments(
            clasificados, {seg["position"]: seg["text"] for seg in segments}
        )

    xml_vista = blocks_to_xml(blocks)
    baseline_texts = [
        block["text"] for block in blocks if block["class"] == "baseline_data"
    ]

    _persistir_metadatos(
        session,
        documento_id,
        {
            "glaser_blocks": blocks,
            "texto_clasificado": xml_vista,
            "baseline_tags": baseline_texts,
            "glaser_used_fallback": used_fallback,
        },
    )

    resultado.update(
        {
            "blocks": blocks,
            "segments": len(clasificados),
            "used_fallback": used_fallback,
            "baseline_tags_count": len(baseline_texts),
            "segments_classified": len(clasificados),
        }
    )

    logger.info(
        "classify_document doc=%s segments=%d blocks=%d baseline=%d fallback=%s",
        documento_id[:8],
        len(clasificados),
        len(blocks),
        len(baseline_texts),
        used_fallback,
    )
    return resultado


# ═══════════════════════════════════════════════════════════════════════
# Camino canónico: clasificación del TEXTO (sin crear segmentos)
# ═══════════════════════════════════════════════════════════════════════


def _blocks_with_offsets(blocks: list[dict], spans: list[dict]) -> list[dict]:
    """Añade `start_char` / `end_char` a los bloques fusionados.

    `merge_adjacent_segments` fusiona por `posicion` y no conoce offsets, pero
    la herencia de tags (`services.glaser_inheritance.inherit_tags`) necesita
    el rango en el texto ORIGINAL para asignar cada segmento a su bloque. Se
    toma el mínimo/máximo de los spans miembros; si alguno no se pudo anclar,
    el offset correspondiente queda en `None` y la herencia cae al match por
    texto normalizado.
    """
    offsets = {
        span["position"]: (span.get("start_char"), span.get("end_char"))
        for span in spans
    }
    for block in blocks:
        positions = block.get("segment_positions") or []
        starts = [
            offsets[p][0]
            for p in positions
            if offsets.get(p) and offsets[p][0] is not None
        ]
        ends = [
            offsets[p][1]
            for p in positions
            if offsets.get(p) and offsets[p][1] is not None
        ]
        block["start_char"] = min(starts) if starts else None
        block["end_char"] = max(ends) if ends else None
    return blocks


def classify_text_spans(
    session, documento_id: str, proyecto_id: str, llm_client
) -> dict:
    """Etiqueta el TEXTO completo en las 5 categorías sin crear segmentos.

    Camino classify-first: reutiliza `llm_segment_and_classify` (el LLM separa
    spans y los categoriza) pero NO llama a `_persistir_segmentos_fallback`.
    Persiste `glaser_blocks`, `texto_clasificado`, `baseline_tags` y
    `glaser_used_fallback=False`. `classify_document` queda para el camino
    legacy (clasificar segmentos existentes / segmentar con el LLM).

    Returns:
        ``{"status": "ok"|"degraded", "reason": ..., "blocks": [...],
        "baseline_tags_count": int}``. Degradar NO lanza: el llamador decide
        (worker → estado 'error' y reintento; tarea de reparación → continuar).
    """
    resultado: dict[str, Any] = {
        "status": "ok",
        "reason": None,
        "blocks": [],
        "baseline_tags_count": 0,
    }

    meta = _documento_metadatos(session, documento_id)
    raw_text = _raw_text_de(meta)
    if not raw_text:
        resultado["status"] = "degraded"
        resultado["reason"] = "document has no text to classify"
        return resultado

    try:
        spans = llm_segment_and_classify(raw_text, proyecto_id, llm_client)
    except Exception as exc:  # noqa: BLE001 - el llamador decide degradar
        logger.error(
            "Clasificación de texto no disponible doc=%s: %s",
            documento_id[:8],
            exc,
        )
        resultado["status"] = "degraded"
        resultado["reason"] = f"llm classification failed: {exc}"
        return resultado

    if not spans:
        resultado["status"] = "degraded"
        resultado["reason"] = "llm returned no spans"
        return resultado

    clasificados = [
        {
            "position": span["position"],
            "category": span["category"],
            "confidence": span["confidence"],
        }
        for span in spans
    ]
    blocks = merge_adjacent_segments(
        clasificados, {span["position"]: span["text"] for span in spans}
    )
    blocks = _blocks_with_offsets(blocks, spans)
    baseline_texts = [
        block["text"] for block in blocks if block["class"] == "baseline_data"
    ]

    _persistir_metadatos(
        session,
        documento_id,
        {
            "glaser_blocks": blocks,
            "texto_clasificado": blocks_to_xml(blocks),
            "baseline_tags": baseline_texts,
            "glaser_used_fallback": False,
        },
    )

    resultado.update(
        {
            "blocks": blocks,
            "baseline_tags_count": len(baseline_texts),
        }
    )
    logger.info(
        "classify_text_spans doc=%s spans=%d blocks=%d baseline=%d",
        documento_id[:8],
        len(spans),
        len(blocks),
        len(baseline_texts),
    )
    return resultado
