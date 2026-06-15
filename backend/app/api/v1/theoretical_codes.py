"""T14 — API de códigos teóricos (built-in + user-defined)."""

from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["theoretical-codes"])


@router.get("/projects/{project_id}/theoretical/codes")
async def list_theoretical_codes(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Lista códigos built-in (globales) + user-defined del proyecto."""
    rows = await db.execute(
        text(
            "SELECT id, name, family, description, glaserian, user_defined, "
            "evaluation_logic, compatible_with, layer, visualization_hint "
            "FROM theoretical_codes "
            "WHERE project_id IS NULL OR project_id = :pid "
            "ORDER BY glaserian DESC, name"
        ),
        {"pid": project_id},
    )
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "family": r[2],
            "description": r[3],
            "glaserian": r[4],
            "user_defined": r[5],
            "evaluation_logic": r[6],
            "compatible_with": r[7],
            "layer": r[8],
            "visualization_hint": r[9],
        }
        for r in rows.fetchall()
    ]


@router.get("/projects/{project_id}/theoretical/codes/{code_id}")
async def get_theoretical_code(
    project_id: UUID,
    code_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Ver un código teórico con su lógica de evaluación completa."""
    row = await db.execute(
        text(
            "SELECT id, name, family, description, glaserian, user_defined, "
            "evaluation_logic, output_schema, compatible_with, layer, visualization_hint "
            "FROM theoretical_codes WHERE id = :cid"
        ),
        {"cid": code_id},
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(404, "Código teórico no encontrado")
    return {
        "id": str(r[0]),
        "name": r[1],
        "family": r[2],
        "description": r[3],
        "glaserian": r[4],
        "user_defined": r[5],
        "evaluation_logic": r[6],
        "output_schema": r[7],
        "compatible_with": r[8],
        "layer": r[9],
        "visualization_hint": r[10],
    }


@router.post("/projects/{project_id}/theoretical/codes", status_code=201)
async def create_theoretical_code(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Crear código teórico user-defined para este proyecto."""
    await db.execute(
        text(
            "INSERT INTO theoretical_codes "
            "(id, project_id, name, family, description, glaserian, user_defined, "
            "evaluation_logic, output_schema, compatible_with, layer, visualization_hint) "
            "VALUES (gen_random_uuid(), :pid, :name, :family, :desc, false, true, "
            ":logic, :schema, :compat, :layer, :viz)"
        ),
        {
            "pid": project_id,
            "name": body.get("name", ""),
            "family": body.get("family", "custom"),
            "desc": body.get("description", ""),
            "logic": body.get("evaluation_logic", {}),
            "schema": body.get("output_schema", {}),
            "compat": body.get("compatible_with", []),
            "layer": body.get("layer", "undefined"),
            "viz": body.get("visualization_hint", "tendril"),
        },
    )
    await db.commit()
    return {"status": "created"}


@router.put("/projects/{project_id}/theoretical/codes/{code_id}")
async def update_theoretical_code(
    project_id: UUID,
    code_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Modificar código user-defined (incluyendo evaluation_logic)."""
    row = await db.execute(
        text(
            "SELECT id FROM theoretical_codes WHERE id = :cid AND user_defined = true"
        ),
        {"cid": code_id},
    )
    if not row.fetchone():
        raise HTTPException(404, "Código no encontrado o no es user-defined")

    await db.execute(
        text(
            "UPDATE theoretical_codes SET "
            "name = COALESCE(:name, name), "
            "description = COALESCE(:desc, description), "
            "evaluation_logic = COALESCE(:logic, evaluation_logic), "
            "compatible_with = COALESCE(:compat, compatible_with), "
            "layer = COALESCE(:layer, layer), "
            "visualization_hint = COALESCE(:viz, visualization_hint) "
            "WHERE id = :cid"
        ),
        {
            "name": body.get("name"),
            "desc": body.get("description"),
            "logic": body.get("evaluation_logic"),
            "compat": body.get("compatible_with"),
            "layer": body.get("layer"),
            "viz": body.get("visualization_hint"),
            "cid": code_id,
        },
    )
    await db.commit()
    return {"status": "updated"}
