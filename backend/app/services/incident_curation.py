"""Curación manual de incidentes: lectura compartida y reglas de integridad.

Este módulo existe para que ``GET /documents/{id}/incidents`` y los endpoints de
curación devuelvan **exactamente la misma forma**. Si cada uno armara su propio
payload, la UI tendría dos representaciones del mismo dato y una de las dos se
quedaría atrás.

``incident_segmentos`` es la fuente de verdad de "qué texto sostiene este
incidente"; ``extracted_incidents.segmento_id`` es una cita primaria
denormalizada que se recalcula en cada mutación.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.services.pipeline_state import pipeline_really_running
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Vocabulario Glaser canónico. Vive también en `projects.GLASER_TAGS` y en
#: `segment_classifier.CLASSES_GLASER`; un test canario verifica que coincidan.
ALLOWED_TAGS: tuple[str, ...] = (
    "baseline_data",
    "properline_data",
    "interpreted_data",
    "vague_data",
    "document_context",
)

#: Alias heredados que el clasificador todavía puede emitir.
_TAG_ALIASES = {
    "baseline": "baseline_data",
    "properline": "properline_data",
    "interpreted": "interpreted_data",
    "vague": "vague_data",
}


def canonical_tag(value: str | None) -> str | None:
    """Normaliza una categoría Glaser. Devuelve None para vacío/null."""
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned:
        return None
    return _TAG_ALIASES.get(cleaned, cleaned)


def validate_tag(value: str | None) -> str | None:
    """Como :func:`canonical_tag` pero rechaza valores fuera del vocabulario."""
    tag = canonical_tag(value)
    if tag is not None and tag not in ALLOWED_TAGS:
        raise HTTPException(
            422,
            f"Categoría Glaser desconocida: '{value}'. "
            f"Valores permitidos: {', '.join(ALLOWED_TAGS)}.",
        )
    return tag


_INCIDENTS_SQL = """
SELECT ei.id,
       ei.segmento_id,
       ei.jot_text,
       ei.keep_moving,
       ei.tipo_dato_glaser,
       ei.origen,
       ei.preguntas_glaser_json,
       COALESCE(
           jsonb_agg(
               jsonb_build_object(
                   'segmento_id', s.id,
                   'posicion', s.posicion,
                   'texto', s.texto,
                   'categoria', COALESCE(x.tipo_dato_glaser, s.tipo_dato_glaser),
                   'categoria_origen', CASE
                       WHEN x.tipo_dato_glaser IS NULL THEN 'segment'
                       ELSE 'override'
                   END,
                   'is_manual', x.is_manual,
                   'primario', (s.id = ei.segmento_id)
               ) ORDER BY s.posicion
           ) FILTER (WHERE s.id IS NOT NULL),
           '[]'::jsonb
       ) AS segments
FROM extracted_incidents ei
LEFT JOIN incident_segmentos x ON x.incident_id = ei.id
LEFT JOIN segmentos s          ON s.id = x.segmento_id
WHERE ei.documento_id = :did
GROUP BY ei.id
ORDER BY ei.creado_en ASC
"""


async def build_incidents_payload(db: AsyncSession, document_id: UUID) -> dict:
    """Incidentes del documento con sus citas, más el prime mover del proceso."""
    rows = await db.execute(text(_INCIDENTS_SQL), {"did": document_id})

    incidents: list[dict] = []
    for row in rows:
        segments = row[7] if isinstance(row[7], list) else []
        categorias: dict[str, int] = {}
        for seg in segments:
            tag = seg.get("categoria") or "sin_categoria"
            categorias[tag] = categorias.get(tag, 0) + 1
        incidents.append(
            {
                "id": str(row[0]),
                "segmento_id": str(row[1]) if row[1] else None,
                "jot_text": row[2],
                "keep_moving": bool(row[3]),
                "tipo_dato_glaser": row[4],
                "origen": row[5] or "ia",
                "preguntas_glaser_json": row[6] if isinstance(row[6], dict) else {},
                "segments": segments,
                "categorias": categorias,
                "mixto": len(categorias) > 1,
            }
        )

    proc = await db.execute(
        text(
            "SELECT prime_mover, prime_mover_confidence "
            "FROM document_processes WHERE documento_id = :did "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"did": document_id},
    )
    proc_row = proc.first()

    return {
        "incidents": incidents,
        "prime_mover": proc_row[0] if proc_row else None,
        "prime_mover_confidence": proc_row[1] if proc_row else None,
    }


_UNASSIGNED_SQL = """
SELECT s.id, s.posicion, s.tipo_dato_glaser, s.texto,
       s.first_10, s.start_char, s.end_char
FROM segmentos s
WHERE s.documento_id = :did
  AND NOT EXISTS (
      SELECT 1 FROM incident_segmentos x WHERE x.segmento_id = s.id
  )
ORDER BY s.posicion
"""


async def build_unassigned_payload(db: AsyncSession, document_id: UUID) -> dict:
    """Segmentos del documento que ningún incidente cita.

    El pool "sin asignar" es derivado a propósito: persistirlo obligaría a
    mantenerlo sincronizado con cada mutación, y se desincronizaría justo cuando
    importa.
    """
    rows = await db.execute(text(_UNASSIGNED_SQL), {"did": document_id})
    segments = [
        {
            "id": str(row[0]),
            "posicion": row[1],
            "tipo_dato_glaser": row[2],
            "texto": row[3],
            "first_10": row[4],
            "start_char": row[5],
            "end_char": row[6],
        }
        for row in rows
    ]

    counts = await db.execute(
        text(
            "SELECT COUNT(*), "
            "COUNT(*) FILTER (WHERE tipo_dato_glaser = 'baseline_data'), "
            "COUNT(*) FILTER (WHERE tipo_dato_glaser IS DISTINCT FROM 'baseline_data') "
            "FROM segmentos WHERE documento_id = :did"
        ),
        {"did": document_id},
    )
    count_row = counts.first()
    total = int(count_row[0] or 0) if count_row else 0
    baseline = int(count_row[1] or 0) if count_row else 0
    non_baseline = int(count_row[2] or 0) if count_row else 0

    return {
        "document_id": str(document_id),
        "segments": segments,
        "counts": {
            "total": total,
            "unassigned": len(segments),
            "baseline": baseline,
            "non_baseline": non_baseline,
        },
    }


async def assert_curation_allowed(
    db: AsyncSession, document_id: UUID, project_id: UUID
) -> None:
    """Bloquea la curación mientras el pipeline trabaja en el proyecto.

    Dos capas, porque resuelven problemas distintos:

    1. ``pipeline_really_running`` pregunta a Celery. Es la verdad de "hay un
       run vivo", pero puede comitear (``heal=True``), así que corre fuera del
       bloque atómico — igual que ``memos.create_user_memo``.
    2. ``pg_try_advisory_xact_lock`` con la MISMA clave que toma
       ``pattern_extractor.extract_patterns_and_incidents``. Eso cubre la
       carrera que (1) no ve: el extractor retiene ese lock durante toda la
       llamada al LLM, mientras el run ya figura como 'running'... o justo
       antes de figurar. Usa ``try_`` y no ``lock`` para no colgar el request
       esperando un PRO call de minutos.
    """
    if await pipeline_really_running(db, project_id, heal=True):
        raise HTTPException(
            409,
            "No se pueden editar incidentes mientras el pipeline está ejecutándose. "
            "Pausalo primero.",
        )

    # `get_current_user` ya abrió una transacción con su SELECT; el bloque
    # atómico del endpoint necesita ser dueño de la suya.
    if db.in_transaction():
        await db.commit()


async def acquire_document_lock(db: AsyncSession, document_id: UUID) -> None:
    """Toma el advisory lock del documento dentro de la transacción en curso."""
    got = (
        await db.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
            {"key": f"extract_incidents:{document_id}"},
        )
    ).scalar()
    if not got:
        raise HTTPException(
            409,
            "El pipeline está extrayendo incidentes de este documento. "
            "Esperá a que termine o pausalo.",
        )


async def recompute_primary(db: AsyncSession, incident_id: UUID) -> None:
    """Reapunta la cita primaria a la primera cita en orden de documento."""
    await db.execute(
        text(
            "UPDATE extracted_incidents ei "
            "SET segmento_id = sub.segmento_id, "
            "    tipo_dato_glaser = COALESCE(sub.categoria, ei.tipo_dato_glaser) "
            "FROM ( "
            "    SELECT s.id AS segmento_id, "
            "           COALESCE(x.tipo_dato_glaser, s.tipo_dato_glaser) AS categoria "
            "    FROM incident_segmentos x "
            "    JOIN segmentos s ON s.id = x.segmento_id "
            "    WHERE x.incident_id = :iid "
            "    ORDER BY s.posicion "
            "    LIMIT 1 "
            ") sub "
            "WHERE ei.id = :iid"
        ),
        {"iid": incident_id},
    )


async def document_of_incident(
    db: AsyncSession, incident_id: UUID
) -> tuple[UUID, UUID]:
    """Devuelve (documento_id, proyecto_id) o 404."""
    row = (
        await db.execute(
            text(
                "SELECT documento_id, proyecto_id FROM extracted_incidents "
                "WHERE id = :iid"
            ),
            {"iid": incident_id},
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Incidente no encontrado")
    return row[0], row[1]


async def document_of_document(db: AsyncSession, document_id: UUID) -> UUID:
    """Devuelve el proyecto_id del documento o 404."""
    row = (
        await db.execute(
            text("SELECT proyecto_id FROM documentos WHERE id = :did"),
            {"did": document_id},
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Documento no encontrado")
    return row[0]
