"""T11 — rename_detector.py

Detecta cuándo una categoría es candidata a renombre.
Combina lógica algorítmica (thresholds) + LLM (generación de sugerencias vía f6b_rename_suggester.md).
Usado por SelectiveElaborator en Fase 5b y por el Theoretical Playground en Fase 6b.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def should_suggest_rename(category_id: UUID, session: Session) -> bool:
    """
    Una categoría es candidata a renombre cuando:
    - Su definición tiene ≥ 3 versiones registradas, O
    - Las propiedades crecieron ≥ 2x desde la versión 1, O
    - Los incidentes crecieron ≥ 3x desde la versión 1.
    """
    versions = session.execute(
        text(
            "SELECT version, properties_at_version, incident_count_at_version "
            "FROM category_definition_versions "
            "WHERE category_id = :cid ORDER BY version"
        ),
        {"cid": category_id},
    ).fetchall()

    if len(versions) < 3:
        return False

    first = versions[0]
    latest = versions[-1]

    first_props = len(first[1]) if isinstance(first[1], dict) else 0
    latest_props = len(latest[1]) if isinstance(latest[1], dict) else 0
    property_growth = latest_props / max(first_props, 1)

    first_incidents = first[2] or 1
    latest_incidents = latest[2] or first_incidents
    incident_growth = latest_incidents / max(first_incidents, 1)

    return property_growth >= 2.0 or incident_growth >= 3.0


def get_rename_candidates(
    category_id: UUID, session: Session, llm_client
) -> Optional[dict]:
    """
    Genera sugerencias de renombre usando f6b_rename_suggester.md.
    Retorna None si el LLM considera que el nombre actual es adecuado.
    """
    cat = session.execute(
        text(
            "SELECT c.nombre, c.definicion, c.version "
            "FROM categorias c WHERE c.id = :cid"
        ),
        {"cid": category_id},
    ).fetchone()

    if not cat:
        return None

    first_version = session.execute(
        text(
            "SELECT name_at_version, definition_at_version "
            "FROM category_definition_versions "
            "WHERE category_id = :cid ORDER BY version LIMIT 1"
        ),
        {"cid": category_id},
    ).fetchone()

    growth = session.execute(
        text(
            "SELECT COUNT(*) FROM category_definition_versions "
            "WHERE category_id = :cid AND trigger LIKE 'incident_diverged%'"
        ),
        {"cid": category_id},
    ).fetchone()[0]

    core = session.execute(
        text(
            "SELECT supuesto_poblacional FROM proyectos "
            "WHERE id = (SELECT proyecto_id FROM categorias WHERE id = :cid)"
        ),
        {"cid": category_id},
    ).fetchone()

    response = llm_client.run_agent(
        "f6b_rename_suggester",
        variables={
            "category_name": cat[0],
            "category_definition": cat[1] or "",
            "version": str(cat[2] or 1),
            "original_name": first_version[0] if first_version else cat[0],
            "original_definition": first_version[1] if first_version else cat[1],
            "properties_growth_summary": f"{growth} expansiones por incidentes divergentes",
            "incident_count": str(
                session.execute(
                    text(
                        "SELECT COUNT(*) FROM codigos_segmento WHERE categoria_id = :cid"
                    ),
                    {"cid": category_id},
                ).fetchone()[0]
            ),
            "core_concern": core[0] if core and core[0] else "(no definido aún)",
        },
        temperature=0.4,
    )

    if response.get("name_is_adequate"):
        return None

    return {
        "category_id": str(category_id),
        "current_name": cat[0],
        "suggestions": response.get("suggestions", []),
    }


def apply_rename(
    category_id: UUID, new_name: str, rationale: str, session: Session
) -> None:
    """Aplica un renombre y registra la nueva versión en el historial."""
    cat = session.execute(
        text("SELECT nombre, definicion, version FROM categorias WHERE id = :cid"),
        {"cid": category_id},
    ).fetchone()

    if not cat:
        return

    old_name = cat[0]
    definition = cat[1]
    version = (cat[2] or 0) + 1

    # Actualizar nombre
    session.execute(
        text("UPDATE categorias SET nombre = :name, version = :v WHERE id = :cid"),
        {"name": new_name, "v": version, "cid": category_id},
    )

    # Registrar en historial
    session.execute(
        text(
            "INSERT INTO category_definition_versions "
            "(id, category_id, project_id, version, name_at_version, "
            "definition_at_version, trigger, trigger_detail) "
            "VALUES (gen_random_uuid(), :cid, "
            "(SELECT proyecto_id FROM categorias WHERE id = :cid2), "
            ":v, :name, :def, 'rename_applied', :detail)"
        ),
        {
            "cid": category_id,
            "cid2": category_id,
            "v": version,
            "name": new_name,
            "def": definition,
            "detail": f"Renombrado de '{old_name}' → '{new_name}'. {rationale}",
        },
    )

    session.commit()
    logger.info("Renamed category %s: '%s' → '%s'", category_id, old_name, new_name)
