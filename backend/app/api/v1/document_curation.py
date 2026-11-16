"""Endpoints de edición manual del resultado del pipeline, por documento.

Dos operaciones, una por paso:

* ``PATCH /documents/{id}/classification`` — cambia (o borra) la categoría de un
  bloque del texto clasificado y vuelve a derivar la etiqueta de los segmentos.
* ``DELETE /documents/{id}/segments/{segment_id}`` — borra un segmento; si el
  siguiente comparte categoría, el texto se fusiona con él.

Reglas compartidas con la curación de incidentes (``api/v1/incidents.py``):

* Toda mutación exige que el pipeline NO esté corriendo (409) y toma el advisory
  lock del documento — el mismo que retiene el extractor.
* La mutación devuelve el estado resultante (bloques o segmentos ya
  persistidos) para que la UI escriba la respuesta en su caché en vez de
  releer.

La lógica de negocio vive en :mod:`app.services.glaser_curation`; acá sólo se
valida la entrada y se delimita la transacción.
"""

from __future__ import annotations

from uuid import UUID

from app.db.database import get_db
from app.models.domain.segment import Segmento
from app.models.domain.user import Usuario
from app.schemas import SegmentResponse
from app.services.auth import get_current_user
from app.services.glaser_curation import (
    absorb_segment,
    apply_class_updates,
    incident_ids_citing,
    normalize_class,
    persist_classification,
    rederive_segment_tags,
    remove_segment,
    renumber_segments,
    scrub_segment_refs,
)
from app.services.incident_curation import (
    acquire_document_lock,
    assert_curation_allowed,
    document_of_document,
    validate_tag,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["document-curation"])

_SEGMENT_COLUMNS = "id, posicion, texto, tipo_dato_glaser, start_char, end_char"


# ── Schemas ──────────────────────────────────────────────────────────────


class BlockClassUpdate(BaseModel):
    index: int = Field(..., ge=0, description="Índice en metadatos.glaser_blocks.")
    class_name: str | None = Field(
        None,
        alias="class",
        description="Categoría Glaser. null borra la categoría del bloque.",
    )

    model_config = ConfigDict(populate_by_name=True)


class ClassificationPatchBody(BaseModel):
    blocks: list[BlockClassUpdate] = Field(..., min_length=1, max_length=2000)


# ── Helpers ──────────────────────────────────────────────────────────────


def _row_to_segment(row) -> dict:
    return {
        "id": str(row[0]),
        "posicion": row[1],
        "texto": row[2] or "",
        "tag": row[3],
        "start_char": row[4],
        "end_char": row[5],
    }


async def _segments_payload(db: AsyncSession, document_id: UUID) -> list[dict]:
    """Segmentos del documento con la MISMA forma que ``GET /segments``."""
    rows = (
        await db.execute(
            select(Segmento)
            .where(Segmento.documento_id == document_id)
            .order_by(Segmento.posicion)
        )
    ).scalars()
    return [
        SegmentResponse.model_validate(segment).model_dump(mode="json")
        for segment in rows
    ]


# ── PATCH /documents/{document_id}/classification ────────────────────────


@router.patch("/documents/{document_id}/classification")
async def patch_document_classification(
    document_id: UUID,
    body: ClassificationPatchBody,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Corrige la categoría de uno o más bloques del texto clasificado.

    Borrar la categoría de un bloque (``class: null``) deja su texto visible
    pero sin etiqueta: la vista XML lo emite suelto, ``baseline_tags`` lo
    excluye (la extracción de incidentes sólo lee ``baseline_data``) y los
    segmentos que caen dentro pierden su ``tipo_dato_glaser``.
    """
    project_id = await document_of_document(db, document_id)
    await assert_curation_allowed(db, document_id, project_id)

    async with db.begin():
        await acquire_document_lock(db, document_id)

        row = (
            await db.execute(
                text("SELECT metadatos FROM documentos WHERE id = :did"),
                {"did": document_id},
            )
        ).first()
        meta = dict(row[0] or {}) if row else {}
        blocks = meta.get("glaser_blocks")
        if not isinstance(blocks, list) or not blocks:
            raise HTTPException(409, "El documento todavía no tiene texto clasificado.")

        updates = [(item.index, validate_tag(item.class_name)) for item in body.blocks]
        try:
            changed = apply_class_updates(blocks, updates)
        except (IndexError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

        saved = await persist_classification(db, document_id, blocks)
        full_text = (
            meta.get("texto_preprocesado")
            or meta.get("texto_extraido")
            or meta.get("texto_original")
            or ""
        )
        segments_updated = await rederive_segment_tags(
            db, document_id, blocks, full_text
        )

    return {
        "status": "ok",
        "blocks": blocks,
        "changed": changed,
        "segments_updated": segments_updated,
        **saved,
    }


# ── DELETE /documents/{document_id}/segments/{segment_id} ────────────────


@router.delete("/documents/{document_id}/segments/{segment_id}")
async def delete_document_segment(
    document_id: UUID,
    segment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Borra un segmento, fusionándolo con el siguiente si comparten categoría.

    "Comparten categoría" incluye el caso de dos segmentos sin etiqueta: borrar
    uno y dejar el otro suelto es indistinguible de fusionarlos.

    Devuelve la lista de segmentos ya recompactada: la UI reemplaza su caché sin
    releer y así no puede quedar mostrando ``posicion`` viejas.
    """
    project_id = await document_of_document(db, document_id)
    await assert_curation_allowed(db, document_id, project_id)

    async with db.begin():
        await acquire_document_lock(db, document_id)

        current = (
            await db.execute(
                text(
                    f"SELECT {_SEGMENT_COLUMNS} FROM segmentos "
                    "WHERE id = :sid AND documento_id = :did"
                ),
                {"sid": segment_id, "did": document_id},
            )
        ).first()
        if current is None:
            raise HTTPException(404, "El segmento no pertenece a este documento.")

        following = (
            await db.execute(
                text(
                    f"SELECT {_SEGMENT_COLUMNS} FROM segmentos "
                    "WHERE documento_id = :did AND posicion > :pos "
                    "ORDER BY posicion LIMIT 1"
                ),
                {"did": document_id, "pos": current[1]},
            )
        ).first()

        gone = _row_to_segment(current)
        survivor = _row_to_segment(following) if following is not None else None

        cited_by = await incident_ids_citing(db, segment_id)

        if survivor is not None and normalize_class(gone["tag"]) == normalize_class(
            survivor["tag"]
        ):
            await absorb_segment(db, gone, survivor)
            await scrub_segment_refs(db, document_id, segment_id, survivor["id"])
            action = "merged"
            survivors_to_fix = cited_by
            removed_incidents: list[str] = []
        else:
            removed_incidents = await remove_segment(db, gone, cited_by)
            await scrub_segment_refs(db, document_id, segment_id, None)
            action = "deleted"
            survivors_to_fix = [
                incident_id
                for incident_id in cited_by
                if incident_id not in removed_incidents
            ]

        await renumber_segments(db, document_id)

        segments = await _segments_payload(db, document_id)

    return {
        "status": "ok",
        "action": action,
        "removed_id": gone["id"],
        "survivor_id": survivor["id"] if action == "merged" else None,
        "incidents_deleted": len(removed_incidents),
        "incidents_updated": len(survivors_to_fix),
        "segments": segments,
    }
