"""Endpoints de curación manual de incidentes.

Todo lo que el investigador puede hacerle a un incidente después de que el
extractor lo produjo: crearlo desde una cita, vincularle o desvincularle citas,
cambiar la categoría de una cita, reescribir el jot y borrarlo.

Reglas que valen para todos los endpoints:

* Toda mutación exige que el pipeline NO esté corriendo (409) y toma el advisory
  lock del documento — el mismo que retiene el extractor.
* Toda mutación devuelve **el mismo payload que `GET /documents/{id}/incidents`**,
  así la UI escribe la respuesta en su caché y no hay un segundo GET que pueda
  devolver una forma distinta.
* Una mutación nunca toca `segmentos.tipo_dato_glaser` ni
  `documentos.metadatos.glaser_blocks`: la categoría de una cita es una
  anotación, no una reclasificación del texto.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Literal
from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from app.services.incident_curation import (
    acquire_document_lock,
    assert_curation_allowed,
    build_incidents_payload,
    build_unassigned_payload,
    document_of_document,
    document_of_incident,
    recompute_primary,
    validate_tag,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["incidents"])


# ── Schemas ──────────────────────────────────────────────────────────────


class SegmentRef(BaseModel):
    segmento_id: UUID
    tipo_dato_glaser: str | None = Field(
        None,
        description="Categoría de ESTA cita. Si se omite, hereda la del segmento.",
    )


class CreateIncidentBody(BaseModel):
    segmentos: list[SegmentRef] = Field(..., min_length=1, max_length=20)
    jot_text: str | None = Field(
        None, description="Descripción del incidente. Si se omite, se usa la cita."
    )
    keep_moving: bool = True
    preguntas_glaser_json: dict | None = None


class AttachSegmentsBody(BaseModel):
    segmentos: list[SegmentRef] = Field(..., min_length=1, max_length=20)
    mode: Literal["move", "add"] = Field(
        "move",
        description="'move' saca la cita de cualquier otro incidente; 'add' la comparte.",
    )


class PatchLinkBody(BaseModel):
    tipo_dato_glaser: str | None = Field(
        None, description="null borra el override y hereda la del segmento."
    )


class PatchIncidentBody(BaseModel):
    jot_text: str | None = None
    keep_moving: bool | None = None


# ── Helpers ──────────────────────────────────────────────────────────────


async def _doc_segments(db: AsyncSession, document_id: UUID) -> dict[str, dict]:
    """Segmentos del documento indexados por id en texto.

    Se traen todos y se filtran en Python a propósito: un documento tiene unos
    cientos de segmentos, y así se evita atar los parámetros a un array de UUID
    (que se comporta distinto según el driver).
    """
    rows = await db.execute(
        text(
            "SELECT id, posicion, texto, tipo_dato_glaser FROM segmentos "
            "WHERE documento_id = :did ORDER BY posicion"
        ),
        {"did": document_id},
    )
    return {
        str(row[0]): {
            "id": str(row[0]),
            "posicion": row[1],
            "texto": row[2] or "",
            "tag": row[3],
        }
        for row in rows
    }


async def _resolve_refs(
    db: AsyncSession,
    document_id: UUID,
    refs: list[SegmentRef],
) -> list[tuple[dict, str]]:
    """Valida que cada cita exista en el documento y resuelve su categoría."""
    index = await _doc_segments(db, document_id)
    resolved: list[tuple[dict, str]] = []
    seen: set[str] = set()
    for ref in refs:
        key = str(ref.segmento_id)
        seg = index.get(key)
        if seg is None:
            raise HTTPException(
                404, f"El segmento {key} no pertenece a este documento."
            )
        if key in seen:
            continue
        seen.add(key)
        tag = validate_tag(ref.tipo_dato_glaser) or seg["tag"]
        if tag is None:
            raise HTTPException(
                422,
                f"El segmento {key} no tiene categoría Glaser; "
                "indicá una explícita en la petición.",
            )
        resolved.append((seg, tag))
    resolved.sort(key=lambda pair: pair[0]["posicion"])
    return resolved


async def _link_ids(db: AsyncSession, incident_id: UUID) -> set[str]:
    rows = await db.execute(
        text("SELECT segmento_id FROM incident_segmentos WHERE incident_id = :iid"),
        {"iid": incident_id},
    )
    return {str(row[0]) for row in rows}


# ── POST /documents/{document_id}/incidents ──────────────────────────────


@router.post("/documents/{document_id}/incidents", status_code=201)
async def create_incident(
    document_id: UUID,
    body: CreateIncidentBody,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Crea un incidente a mano a partir de una o varias citas del documento."""
    project_id = await document_of_document(db, document_id)
    await assert_curation_allowed(db, document_id, project_id)

    async with db.begin():
        await acquire_document_lock(db, document_id)

        resolved = await _resolve_refs(db, document_id, body.segmentos)
        primary, primary_tag = resolved[0]

        jot = (body.jot_text or "").strip() or primary["texto"][:200]
        meta = {
            "method": "manual_curation",
            "exact_quote": primary["texto"],
            "segment_refs": [seg["id"] for seg, _ in resolved],
            "patterns": [],
            "created_by": str(current_user.id),
        }
        if body.preguntas_glaser_json:
            meta.update(body.preguntas_glaser_json)

        incident_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO extracted_incidents "
                "(id, segmento_id, documento_id, proyecto_id, jot_text, "
                " keep_moving, tipo_dato_glaser, origen, preguntas_glaser_json) "
                "VALUES (:iid, :sid, :did, :pid, :jot, :km, :tdg, 'manual', "
                "        CAST(:meta AS jsonb))"
            ),
            {
                "iid": incident_id,
                "sid": primary["id"],
                "did": document_id,
                "pid": project_id,
                "jot": jot,
                "km": body.keep_moving,
                "tdg": primary_tag,
                "meta": json.dumps(meta, ensure_ascii=False),
            },
        )
        for seg, tag in resolved:
            await db.execute(
                text(
                    "INSERT INTO incident_segmentos "
                    "(incident_id, segmento_id, tipo_dato_glaser, is_manual) "
                    "VALUES (:iid, :sid, :tdg, true) "
                    "ON CONFLICT (incident_id, segmento_id) DO NOTHING"
                ),
                {"iid": incident_id, "sid": seg["id"], "tdg": tag},
            )

    payload = await build_incidents_payload(db, document_id)
    return {"status": "ok", "incident_id": str(incident_id), **payload}


# ── POST /incidents/{incident_id}/segments ───────────────────────────────


@router.post("/incidents/{incident_id}/segments", status_code=200)
async def attach_segments(
    incident_id: UUID,
    body: AttachSegmentsBody,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Vincula una o varias citas a un incidente existente.

    Es idempotente: un par ya vinculado se informa en ``already_assigned`` y
    **no** se le pisa la categoría (para eso está el PATCH).

    Con ``mode='move'`` la cita se saca del incidente que la tuviera. Eso no
    puede dejar a ese incidente sin ninguna cita —es el estado que
    ``DELETE .../segments`` rechaza con 409—, así que se valida antes de tocar
    nada y se le recalcula la cita primaria a los donantes que sobreviven.
    """
    document_id, project_id = await document_of_incident(db, incident_id)
    await assert_curation_allowed(db, document_id, project_id)

    added: list[str] = []
    already: list[str] = []

    async with db.begin():
        await acquire_document_lock(db, document_id)

        resolved = await _resolve_refs(db, document_id, body.segmentos)
        existing = await _link_ids(db, incident_id)

        to_add = [(seg, tag) for seg, tag in resolved if seg["id"] not in existing]
        already = [seg["id"] for seg, _ in resolved if seg["id"] in existing]

        donors: set[UUID] = set()
        if body.mode == "move" and to_add:
            losses: dict[UUID, set[str]] = {}
            for seg, _ in to_add:
                rows = (
                    await db.execute(
                        text(
                            "SELECT incident_id FROM incident_segmentos "
                            "WHERE segmento_id = :sid AND incident_id <> :iid"
                        ),
                        {"sid": seg["id"], "iid": incident_id},
                    )
                ).fetchall()
                for (donor_id,) in rows:
                    losses.setdefault(donor_id, set()).add(seg["id"])

            for donor_id, moved in losses.items():
                total = (
                    await db.execute(
                        text(
                            "SELECT count(*) FROM incident_segmentos "
                            "WHERE incident_id = :iid"
                        ),
                        {"iid": donor_id},
                    )
                ).scalar() or 0
                if total <= len(moved):
                    raise HTTPException(
                        409,
                        "Esa cita es la única de otro incidente. "
                        "Vinculala en modo 'compartir' o borrá ese incidente primero.",
                    )
                donors.add(donor_id)

        for seg, tag in to_add:
            if body.mode == "move":
                await db.execute(
                    text(
                        "DELETE FROM incident_segmentos WHERE segmento_id = :sid "
                        "AND incident_id <> :iid"
                    ),
                    {"sid": seg["id"], "iid": incident_id},
                )
            await db.execute(
                text(
                    "INSERT INTO incident_segmentos "
                    "(incident_id, segmento_id, tipo_dato_glaser, is_manual) "
                    "VALUES (:iid, :sid, :tdg, true) "
                    "ON CONFLICT (incident_id, segmento_id) DO NOTHING"
                ),
                {"iid": incident_id, "sid": seg["id"], "tdg": tag},
            )
            added.append(seg["id"])

        await db.execute(
            text("UPDATE extracted_incidents SET origen = 'manual' WHERE id = :iid"),
            {"iid": incident_id},
        )
        await recompute_primary(db, incident_id)
        for donor_id in donors:
            await recompute_primary(db, donor_id)

    payload = await build_incidents_payload(db, document_id)
    return {
        "status": "ok",
        "added": added,
        "already_assigned": already,
        **payload,
    }


# ── DELETE /incidents/{incident_id}/segments/{segmento_id} ───────────────


@router.delete("/incidents/{incident_id}/segments/{segmento_id}", status_code=200)
async def detach_segment(
    incident_id: UUID,
    segmento_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Desvincula una cita. Se rechaza si era la última.

    Un incidente sin citas deja de ser evidencia: el jot quedaría sostenido por
    nada. El camino correcto en ese caso es borrar el incidente (la cita vuelve
    al pool "sin asignar" igual).
    """
    document_id, project_id = await document_of_incident(db, incident_id)
    await assert_curation_allowed(db, document_id, project_id)

    async with db.begin():
        await acquire_document_lock(db, document_id)

        links = await _link_ids(db, incident_id)
        if str(segmento_id) not in links:
            raise HTTPException(404, "El incidente no cita ese segmento.")
        if len(links) == 1:
            raise HTTPException(
                409,
                "Un incidente no puede quedarse sin cita. "
                "Eliminá el incidente o asignale otra cita primero.",
            )

        await db.execute(
            text(
                "DELETE FROM incident_segmentos "
                "WHERE incident_id = :iid AND segmento_id = :sid"
            ),
            {"iid": incident_id, "sid": segmento_id},
        )
        await db.execute(
            text("UPDATE extracted_incidents SET origen = 'manual' WHERE id = :iid"),
            {"iid": incident_id},
        )
        await recompute_primary(db, incident_id)

        still_linked = (
            await db.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM incident_segmentos "
                    "WHERE segmento_id = :sid)"
                ),
                {"sid": segmento_id},
            )
        ).scalar()

    payload = await build_incidents_payload(db, document_id)
    return {
        "status": "ok",
        "segment_now_unassigned": not still_linked,
        **payload,
    }


# ── PATCH /incidents/{incident_id}/segments/{segmento_id} ────────────────


@router.patch("/incidents/{incident_id}/segments/{segmento_id}", status_code=200)
async def patch_link(
    incident_id: UUID,
    segmento_id: UUID,
    body: PatchLinkBody,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Cambia la categoría de UNA cita (``null`` la hereda del segmento)."""
    document_id, project_id = await document_of_incident(db, incident_id)
    await assert_curation_allowed(db, document_id, project_id)

    tag = validate_tag(body.tipo_dato_glaser)

    async with db.begin():
        await acquire_document_lock(db, document_id)

        links = await _link_ids(db, incident_id)
        if str(segmento_id) not in links:
            raise HTTPException(404, "El incidente no cita ese segmento.")

        await db.execute(
            text(
                "UPDATE incident_segmentos "
                "SET tipo_dato_glaser = :tdg, actualizado_en = now(), is_manual = true "
                "WHERE incident_id = :iid AND segmento_id = :sid"
            ),
            {"tdg": tag, "iid": incident_id, "sid": segmento_id},
        )
        await db.execute(
            text("UPDATE extracted_incidents SET origen = 'manual' WHERE id = :iid"),
            {"iid": incident_id},
        )
        await recompute_primary(db, incident_id)

    return {"status": "ok", **(await build_incidents_payload(db, document_id))}


# ── PATCH /incidents/{incident_id} ───────────────────────────────────────


@router.patch("/incidents/{incident_id}", status_code=200)
async def patch_incident(
    incident_id: UUID,
    body: PatchIncidentBody,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Reescribe el jot y/o el flag keep_moving de un incidente."""
    document_id, project_id = await document_of_incident(db, incident_id)
    if body.jot_text is None and body.keep_moving is None:
        raise HTTPException(422, "Indicá al menos un campo a modificar.")
    await assert_curation_allowed(db, document_id, project_id)

    async with db.begin():
        await acquire_document_lock(db, document_id)

        if body.jot_text is not None:
            jot = body.jot_text.strip()
            if not jot:
                raise HTTPException(
                    422, "El texto del incidente no puede quedar vacío."
                )
            await db.execute(
                text(
                    "UPDATE extracted_incidents "
                    "SET jot_text = :jot, origen = 'manual' WHERE id = :iid"
                ),
                {"jot": jot, "iid": incident_id},
            )
        if body.keep_moving is not None:
            await db.execute(
                text(
                    "UPDATE extracted_incidents "
                    "SET keep_moving = :km, origen = 'manual' WHERE id = :iid"
                ),
                {"km": body.keep_moving, "iid": incident_id},
            )

    return {"status": "ok", **(await build_incidents_payload(db, document_id))}


# ── DELETE /incidents/{incident_id} ──────────────────────────────────────


@router.delete("/incidents/{incident_id}", status_code=200)
async def delete_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra UN incidente. Sus citas no se tocan: vuelven al pool sin asignar.

    ``incident_comparisons`` cae en cascada desde la migración 020, así que
    borrar el incidente arrastra sus pares. ``incident_groups.incident_ids_json``
    es JSONB sin FK: hay que podarlo a mano y borrar los grupos que se quedaron
    sin incidentes.
    """
    document_id, project_id = await document_of_incident(db, incident_id)
    await assert_curation_allowed(db, document_id, project_id)

    async with db.begin():
        await acquire_document_lock(db, document_id)

        freed = sorted(await _link_ids(db, incident_id))

        comparisons = (
            await db.execute(
                text(
                    "DELETE FROM incident_comparisons "
                    "WHERE incident_a_id = :iid OR incident_b_id = :iid"
                ),
                {"iid": incident_id},
            )
        ).rowcount or 0

        await db.execute(
            text("DELETE FROM extracted_incidents WHERE id = :iid"),
            {"iid": incident_id},
        )

        await db.execute(
            text(
                "UPDATE incident_groups g "
                "SET incident_ids_json = COALESCE(("
                "    SELECT jsonb_agg(t.value) "
                "    FROM jsonb_array_elements_text(g.incident_ids_json) AS t(value) "
                "    WHERE t.value <> :iid_text"
                "), '[]'::jsonb) "
                "WHERE g.proyecto_id = :pid "
                "  AND g.incident_ids_json @> to_jsonb(ARRAY[:iid_text]::text[])"
            ),
            {"iid_text": str(incident_id), "pid": project_id},
        )
        groups_deleted = (
            await db.execute(
                text(
                    "DELETE FROM incident_groups "
                    "WHERE proyecto_id = :pid "
                    "AND jsonb_array_length(incident_ids_json) = 0"
                ),
                {"pid": project_id},
            )
        ).rowcount or 0

    return {
        "status": "ok",
        "deleted": True,
        "incident_id": str(incident_id),
        "comparisons_deleted": comparisons,
        "groups_deleted": groups_deleted,
        "freed_segment_ids": freed,
        **(await build_incidents_payload(db, document_id)),
    }


# ── GET /documents/{document_id}/unassigned-segments ─────────────────────


@router.get("/documents/{document_id}/unassigned-segments")
async def list_unassigned_segments(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Segmentos del documento que ningún incidente cita.

    Es el pool al que vuelve una cita cuando se borra su incidente, y la razón
    por la que "excluidos por tipo" dejan de ser un callejón sin salida.
    """
    return await build_unassigned_payload(db, document_id)
