"""Edición manual del resultado del pipeline Glaser, por documento.

Dos superficies, una por paso de la escalera:

* **clasificado** — el investigador corrige la categoría de un bloque del texto
  (``metadatos.glaser_blocks``) o la borra. Editar la clasificación no es
  cosmético: ``segmentos.tipo_dato_glaser`` es una copia **derivada** de los
  bloques (ver :mod:`app.services.glaser_inheritance`), así que después del
  edit hay que volver a derivarla o la extracción de incidentes seguiría leyendo
  la categoría vieja.
* **segmentado** — el investigador borra un segmento. Si el siguiente comparte
  categoría se fusiona con él (el texto sobrevive en la fila de al lado); si no,
  desaparece. En ambos casos hay que recompactar ``posicion`` y reubicar todo lo
  que apunta al segmento borrado: ``incident_segmentos`` y
  ``codigos_segmento.segmento_id`` (la segunda es FK ``NO ACTION``: Postgres
  rechaza el DELETE si quedan filas).

Las reglas de concurrencia —pipeline detenido + advisory lock del documento—
viven en :mod:`app.services.incident_curation` y se reutilizan tal cual: el
extractor de incidentes toca el mismo documento, así que una edición a mitad de
corrida produciría exactamente el mismo desastre.

Las funciones de este módulo asumen que quien las llama ya está **dentro** de
una transacción; no abren ni cierran ninguna.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.services.glaser_inheritance import inherit_tags
from app.services.incident_curation import ALLOWED_TAGS, canonical_tag
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Etiquetas de la taxonomía vieja. El clasificador ya no las emite, pero los
#: documentos clasificados antes del rediseño las conservan y hay que seguir
#: traduciéndolas al regenerar la vista.
_LEGACY_CLASS_ALIASES: dict[str, str] = {
    "processual_data": "baseline_data",
    "contextual_data": "vague_data",
    "interviewer_context": "document_context",
}


# ── Bloque → texto clasificado ───────────────────────────────────────────


def normalize_class(value: Any) -> str | None:
    """Categoría canónica de un bloque. ``None`` = bloque sin categoría.

    No valida contra el vocabulario: una etiqueta desconocida se devuelve tal
    cual, porque mostrar una categoría rara es mejor que inventar una
    clasificación.
    """
    if value is None:
        return None
    tag = canonical_tag(value)
    if tag is None:
        return None
    return _LEGACY_CLASS_ALIASES.get(tag, tag)


def blocks_to_classified_xml(blocks: list[dict]) -> str:
    """Vista XML del texto clasificado.

    Los bloques sin categoría se emiten **como texto suelto**: borrar una
    categoría no puede borrar el texto del documento.
    """
    parts: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        body = (block.get("text") or "").strip()
        if not body:
            continue
        tag = normalize_class(block.get("class"))
        parts.append(f"<{tag}>{body}</{tag}>" if tag else body)
    return "\n\n".join(parts)


def baseline_texts(blocks: list[dict]) -> list[str]:
    """Textos ``baseline_data``: lo único que alimenta la extracción de incidentes."""
    out: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        if normalize_class(block.get("class")) != "baseline_data":
            continue
        body = (block.get("text") or "").strip()
        if body:
            out.append(body)
    return out


def apply_class_updates(
    blocks: list[dict], updates: list[tuple[int, str | None]]
) -> int:
    """Aplica ``(índice, categoría)`` sobre los bloques, EN SU LUGAR.

    El índice es el de ``metadatos.glaser_blocks`` tal cual lo ve la UI, así que
    la lista **no** se filtra antes de indexar: un bloque sin categoría sigue
    contando (si se filtrara, el primer edit desplazaría todos los índices).

    Returns:
        Cuántos bloques cambiaron realmente.

    Raises:
        IndexError: el índice no existe.
        ValueError: el bloque destino no tiene texto.
    """
    changed = 0
    for index, tag in updates:
        if index < 0 or index >= len(blocks):
            raise IndexError(f"no existe el bloque {index}")
        block = blocks[index]
        if not isinstance(block, dict) or not isinstance(block.get("text"), str):
            raise ValueError(f"el bloque {index} no tiene texto clasificado")
        if normalize_class(block.get("class")) == tag:
            continue
        block["class"] = tag
        changed += 1
    return changed


async def persist_classification(
    db: AsyncSession, document_id: UUID, blocks: list[dict]
) -> dict:
    """Escribe bloques + las vistas derivadas que leen el resto de las etapas."""
    xml = blocks_to_classified_xml(blocks)
    baselines = baseline_texts(blocks)
    patch = {
        "glaser_blocks": blocks,
        "texto_clasificado": xml,
        "baseline_tags": baselines,
    }
    await db.execute(
        text(
            "UPDATE documentos SET metadatos = "
            "COALESCE(metadatos, '{}'::jsonb) || CAST(:patch AS jsonb) "
            "WHERE id = :did"
        ),
        {"patch": json.dumps(patch, ensure_ascii=False), "did": document_id},
    )
    return {"texto_clasificado": xml, "baseline_tags_count": len(baselines)}


async def rederive_segment_tags(
    db: AsyncSession,
    document_id: UUID,
    blocks: list[dict],
    full_text: str,
) -> int:
    """Reasigna ``segmentos.tipo_dato_glaser`` desde los bloques.

    Usa la MISMA herencia que la segmentación
    (:func:`app.services.glaser_inheritance.inherit_tags`), así que editar y
    deshacer universos deja el documento en el mismo estado que si nunca se
    hubiera tocado (verificado sobre los 5 documentos del proyecto de prueba).

    Nunca inventa categoría: si la herencia no puede decidir, el segmento queda
    sin etiqueta y el detector de inconsistencias lo ve.

    Returns:
        Cuántos segmentos cambiaron de etiqueta.
    """
    rows = (
        await db.execute(
            text(
                "SELECT id, texto, tipo_dato_glaser FROM segmentos "
                "WHERE documento_id = :did ORDER BY posicion"
            ),
            {"did": document_id},
        )
    ).fetchall()
    if not rows:
        return 0

    derived = inherit_tags([row[1] or "" for row in rows], blocks, full_text)
    updated = 0
    matched = 0
    for row, tag in zip(rows, derived):
        new_tag = normalize_class(tag)
        if new_tag is not None and new_tag not in ALLOWED_TAGS:
            # Etiqueta que no reconocemos: no la propagamos a los segmentos.
            logger.debug(
                "Herencia Doc=%s: etiqueta desconocida %r ignorada",
                str(document_id)[:8],
                new_tag,
            )
            continue
        if new_tag:
            matched += 1
        if (row[2] or None) == new_tag:
            continue
        await db.execute(
            text("UPDATE segmentos SET tipo_dato_glaser = :tag WHERE id = :sid"),
            {"tag": new_tag, "sid": row[0]},
        )
        updated += 1

    # Los contadores que muestra la UI quedarían mintiendo si no se refrescan.
    counters = {
        "glaser_inheritance": {
            "matched": matched,
            "unmatched": len(rows) - matched,
            "total": len(rows),
        }
    }
    await db.execute(
        text(
            "UPDATE documentos SET metadatos = "
            "COALESCE(metadatos, '{}'::jsonb) || CAST(:patch AS jsonb) "
            "WHERE id = :did"
        ),
        {"patch": json.dumps(counters), "did": document_id},
    )
    return updated


# ── Segmentos: fusión y borrado ──────────────────────────────────────────


def merge_spans(
    first: tuple[int | None, int | None], second: tuple[int | None, int | None]
) -> tuple[int | None, int | None]:
    """Unión de dos rangos de caracteres, ignorando los que no están anclados."""
    starts = [value for value in (first[0], second[0]) if value is not None]
    ends = [value for value in (first[1], second[1]) if value is not None]
    return (
        min(starts) if starts else None,
        max(ends) if ends else None,
    )


def join_segment_text(first: str, second: str) -> str:
    """Une dos segmentos con un único espacio (no duplica puntuación)."""
    return " ".join(
        part for part in ((first or "").strip(), (second or "").strip()) if part
    )


def first_ten_words(text: str) -> str:
    """Ancla textual para la reconstrucción determinista (igual que ``_anchor_segments``)."""
    words = (text or "").split()
    anchor = " ".join(words[:10]) if len(words) >= 10 else (text or "")[:100]
    return anchor[:200]


async def incident_ids_citing(db: AsyncSession, segment_id: UUID) -> list[str]:
    """Incidentes que citan el segmento, en orden estable."""
    rows = await db.execute(
        text(
            "SELECT DISTINCT incident_id FROM incident_segmentos "
            "WHERE segmento_id = :sid"
        ),
        {"sid": segment_id},
    )
    return [str(row[0]) for row in rows]


async def scrub_segment_refs(
    db: AsyncSession,
    document_id: UUID,
    gone_id: UUID,
    survivor_id: UUID | None,
) -> None:
    """Reescribe ``preguntas_glaser_json.segment_refs`` para no dejar ids muertos.

    Desde la migración 020 los refs son UUID (los ordinales originales quedaron
    en ``segment_refs_ordinals``), así que un id borrado sólo se puede limpiar
    en Python.
    """
    rows = await db.execute(
        text(
            "SELECT id, preguntas_glaser_json FROM extracted_incidents "
            "WHERE documento_id = :did "
            "AND jsonb_typeof(preguntas_glaser_json->'segment_refs') = 'array'"
        ),
        {"did": document_id},
    )
    gone = str(gone_id)
    for incident_id, preguntas in rows.fetchall():
        refs = (preguntas or {}).get("segment_refs")
        if not isinstance(refs, list) or gone not in [str(ref) for ref in refs]:
            continue
        new_refs: list[str] = []
        for ref in refs:
            value = str(survivor_id) if str(ref) == gone and survivor_id else ref
            if str(value) == gone or str(value) in new_refs:
                continue
            new_refs.append(str(value))
        await db.execute(
            text(
                "UPDATE extracted_incidents SET preguntas_glaser_json = "
                "jsonb_set(preguntas_glaser_json, '{segment_refs}', "
                "CAST(:refs AS jsonb)) WHERE id = :iid"
            ),
            {"refs": json.dumps(new_refs), "iid": incident_id},
        )


async def absorb_segment(db: AsyncSession, gone: dict, survivor: dict) -> None:
    """Fusiona ``gone`` dentro de ``survivor`` y borra la fila sobrante.

    El superviviente es siempre el segmento SIGUIENTE: el botón "borrar" hace
    desaparecer la fila clickeada, así que su texto tiene que sobrevivir en la
    de al lado (y ese es justamente el caso que el investigador quiere).

    Mueve TODO lo que apunta a ``gone`` antes del DELETE — ``codigos_segmento``
    es FK ``NO ACTION`` y bloquea el borrado.
    """
    # Citas: un incidente no pierde evidencia al fusionar segmentos. Esta tabla
    # es la única fuente de verdad de "qué texto sostiene el incidente".
    await db.execute(
        text(
            "INSERT INTO incident_segmentos "
            "(incident_id, segmento_id, tipo_dato_glaser, is_manual) "
            "SELECT incident_id, :surv, tipo_dato_glaser, is_manual "
            "FROM incident_segmentos WHERE segmento_id = :gone "
            "ON CONFLICT (incident_id, segmento_id) DO NOTHING"
        ),
        {"surv": survivor["id"], "gone": gone["id"]},
    )
    # Open coding (fase C) referencia segmentos con el mismo problema.
    await db.execute(
        text(
            "INSERT INTO codigos_segmento (segmento_id, categoria_id) "
            "SELECT :surv, categoria_id FROM codigos_segmento "
            "WHERE segmento_id = :gone "
            "ON CONFLICT (segmento_id, categoria_id) DO NOTHING"
        ),
        {"surv": survivor["id"], "gone": gone["id"]},
    )
    await db.execute(
        text("DELETE FROM codigos_segmento WHERE segmento_id = :gone"),
        {"gone": gone["id"]},
    )

    merged_text = join_segment_text(gone["texto"], survivor["texto"])
    start, end = merge_spans(
        (gone["start_char"], gone["end_char"]),
        (survivor["start_char"], survivor["end_char"]),
    )
    await db.execute(
        text(
            "UPDATE segmentos SET texto = :txt, conteo_tokens = :tok, "
            "tipo_dato_glaser = :tag, first_10 = :f10, "
            "start_char = :sc, end_char = :ec "
            "WHERE id = :sid"
        ),
        {
            "txt": merged_text,
            "tok": len(merged_text.split()),
            "tag": survivor["tag"],
            "f10": first_ten_words(merged_text),
            "sc": start,
            "ec": end,
            "sid": survivor["id"],
        },
    )
    # `incident_segmentos` cae por CASCADE.
    await db.execute(
        text("DELETE FROM segmentos WHERE id = :gone"), {"gone": gone["id"]}
    )


async def remove_segment(
    db: AsyncSession, gone: dict, cited_by: list[str]
) -> list[str]:
    """Borra el segmento y devuelve los incidentes que quedaron sin evidencia.

    Un incidente sin ninguna cita deja de ser evidencia —no hay texto que lo
    sostenga—, así que se borra en vez de quedar apuntando a una fila muerta.
    La cuenta se hace sobre ``incident_segmentos`` (fuente de verdad de las
    citas): si el incidente sólo citaba el segmento que desaparece, queda
    huérfano.
    """
    orphans: list[str] = []
    for incident_id in cited_by:
        total = (
            await db.execute(
                text(
                    "SELECT count(*) FROM incident_segmentos WHERE incident_id = :iid"
                ),
                {"iid": incident_id},
            )
        ).scalar() or 0
        if total <= 1:
            orphans.append(incident_id)

    for incident_id in orphans:
        # `incident_comparisons` es CASCADE desde la 020.
        await db.execute(
            text("DELETE FROM extracted_incidents WHERE id = :iid"),
            {"iid": incident_id},
        )

    await db.execute(
        text("DELETE FROM codigos_segmento WHERE segmento_id = :gone"),
        {"gone": gone["id"]},
    )
    await db.execute(
        text("DELETE FROM segmentos WHERE id = :gone"), {"gone": gone["id"]}
    )
    return orphans


async def renumber_segments(db: AsyncSession, document_id: UUID) -> None:
    """Recompacta ``posicion`` a 1..N preservando el orden.

    No hay índice único sobre ``(documento_id, posicion)``, así que el UPDATE
    masivo es seguro.
    """
    await db.execute(
        text(
            "WITH ordered AS ("
            "  SELECT id, row_number() OVER (ORDER BY posicion) AS rn "
            "  FROM segmentos WHERE documento_id = :did"
            ") "
            "UPDATE segmentos s SET posicion = ordered.rn "
            "FROM ordered "
            "WHERE s.id = ordered.id AND s.posicion <> ordered.rn"
        ),
        {"did": document_id},
    )
