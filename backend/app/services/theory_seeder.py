"""T28 — Seed de 12 códigos teóricos glaserianos built-in.

Se ejecuta al inicializar la BD o al crear un proyecto nuevo.
Los códigos con project_id=NULL son globales (disponibles para todos los proyectos).

F1.3: Los datos canónicos ahora viven en `app.core.theoretical_families`.
"""

from __future__ import annotations

import json
import uuid
from uuid import UUID

from app.core.theoretical_families import THEORETICAL_FAMILIES
from sqlalchemy import text
from sqlalchemy.orm import Session

# Alias para compatibilidad con código existente
BUILT_IN_THEORETICAL_CODES = THEORETICAL_FAMILIES


def seed_theoretical_codes(session: Session) -> int:
    """Inserta los 12 códigos built-in si no existen. Retorna cantidad insertada."""
    existing = session.execute(
        text("SELECT COUNT(*) FROM theoretical_codes WHERE project_id IS NULL")
    ).fetchone()[0]

    if existing >= 12:
        return 0

    inserted = 0
    for code in BUILT_IN_THEORETICAL_CODES:
        row = session.execute(
            text("SELECT id FROM theoretical_codes WHERE id = :id"),
            {"id": code["id"]},
        ).fetchone()
        if row:
            continue

        session.execute(
            text(
                """INSERT INTO theoretical_codes
                (id, project_id, name, family, description, glaserian, user_defined,
                 evaluation_logic, output_schema, compatible_with, layer, visualization_hint)
                VALUES (:id, NULL, :name, :family, :desc, true, false,
                        :logic, :schema, :compat, :layer, :viz)"""
            ),
            {
                "id": code["id"],
                "name": code["name"],
                "family": code["family"],
                "desc": code["description"],
                "logic": json.dumps(code.get("evaluation_logic", {})),
                "schema": json.dumps(code.get("output_schema", {})),
                "compat": json.dumps(code.get("compatible_with", [])),
                "layer": code.get("layer", "undefined"),
                "viz": code.get("visualization_hint", "tendril"),
            },
        )
        inserted += 1

    session.commit()
    return inserted
