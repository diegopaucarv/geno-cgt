"""
B1 — Incident Comparator (PRO, 1-pass).

Compara incidentes extraídos (extracted_incidents) para evaluar
intercambiabilidad entre pares. NO ve categorías ni etiquetas existentes.
Agrupa incidentes intercambiables en incident_groups.

Estrategia incremental:
  - Primera ejecución: compara todos contra todos.
  - Subsecuentes: solo compara incidentes nuevos contra grupos existentes y entre sí.

See AGENTES.md §incident_comparator for I/O spec.
"""

from __future__ import annotations

import json
import logging

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def b1_compare_incidents(proyecto_id: str, incremental: bool = False) -> dict:
    """Compara incidentes extraídos para evaluar intercambiabilidad.

    Lee SOLO de extracted_incidents — NO categorías, NO etiquetas existentes.
    Escribe en incident_comparisons y incident_groups.

    Args:
        proyecto_id: UUID del proyecto.
        incremental: Si True, solo compara incidentes nuevos (sin grupo asignado)
                     contra grupos existentes y entre sí. Si False (primera vez),
                     compara todos contra todos.

    Returns:
        dict con:
          - comparisons_created: int
          - groups_created: int
          - groups_updated: int
          - ungrouped_count: int
          - strategy: "full" | "incremental"
    """
    session = SessionLocal()
    try:
        # ── Determinar estrategia ──────────────────────────────────
        row = session.execute(
            text("SELECT COUNT(*) FROM incident_groups WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        existing_groups = row[0] if row else 0

        if not incremental and existing_groups == 0:
            strategy = "full"
        elif incremental and existing_groups > 0:
            strategy = "incremental"
        elif existing_groups > 0:
            # Ya hay grupos: usar incremental aunque no se pidió explícitamente
            strategy = "incremental"
            logger.info(
                "Project %s: %d existing groups — switching to incremental",
                proyecto_id,
                existing_groups,
            )
        else:
            strategy = "full"

        # ── Cargar incidentes ──────────────────────────────────────
        if strategy == "full":
            rows = session.execute(
                text(
                    "SELECT id, jot_text, preguntas_glaser_json, documento_id "
                    "FROM extracted_incidents "
                    "WHERE proyecto_id = :pid "
                    "ORDER BY creado_en"
                ),
                {"pid": proyecto_id},
            ).fetchall()
        else:
            # Incremental: solo incidentes sin grupo asignado
            rows = session.execute(
                text(
                    "SELECT ei.id, ei.jot_text, ei.preguntas_glaser_json, ei.documento_id "
                    "FROM extracted_incidents ei "
                    "WHERE ei.proyecto_id = :pid "
                    "AND ei.id NOT IN ("
                    "  SELECT jsonb_array_elements_text(ig.incident_ids_json)::uuid "
                    "  FROM incident_groups ig WHERE ig.proyecto_id = :pid2"
                    ") "
                    "ORDER BY ei.creado_en"
                ),
                {"pid": proyecto_id, "pid2": proyecto_id},
            ).fetchall()

        if not rows:
            logger.info("B1: No incidents to compare for project %s", proyecto_id)
            return {
                "comparisons_created": 0,
                "groups_created": 0,
                "groups_updated": 0,
                "ungrouped_count": 0,
                "strategy": strategy,
            }

        incidents = []
        for r in rows:
            glaser = r[2] or {}
            # Construir representación textual rica del incidente
            what_is = glaser.get("what_is_this_about", "")
            what_cat = glaser.get("what_category", "")
            what_happening = glaser.get("what_is_happening", "")
            participants = glaser.get("participants_pattern", "")
            jot = r[1] or ""

            incidents.append(
                {
                    "id": str(r[0]),
                    "jot": jot,
                    "what_is_this_about": what_is,
                    "what_category": what_cat,
                    "what_is_happening": what_happening,
                    "participants_pattern": participants,
                    "documento_id": str(r[3]),
                }
            )

        # ── Preparar variables para el prompt ──────────────────────
        incidents_json = json.dumps(incidents, indent=2, ensure_ascii=False)

        if strategy == "full":
            strategy_note = (
                "PRIMERA EJECUCIÓN. Compara TODOS los incidentes entre sí. "
                "Agrupa los que sean intercambiables. "
                f"Total: {len(incidents)} incidentes."
            )
        else:
            # Cargar resumen de grupos existentes para el incremental
            existing_summary = session.execute(
                text(
                    "SELECT id, label, incident_ids_json "
                    "FROM incident_groups "
                    "WHERE proyecto_id = :pid AND status != 'rejected'"
                ),
                {"pid": proyecto_id},
            ).fetchall()

            summary_parts = []
            for eg in existing_summary:
                gid = str(eg[0])
                label = eg[1] or "(sin etiqueta)"
                inc_count = len(eg[2]) if eg[2] else 0
                summary_parts.append(
                    f"Grupo {gid[:8]}: '{label}' ({inc_count} incidentes)"
                )

            strategy_note = (
                "EJECUCIÓN INCREMENTAL. Ya existen grupos formados:\n"
                + "\n".join(summary_parts)
                + f"\n\nCompara los {len(incidents)} incidentes NUEVOS de abajo "
                "contra estos grupos existentes y entre sí. "
                "Si un incidente nuevo es intercambiable con un grupo existente, "
                "indícalo en los grupos como 'merge_with_existing_group'."
            )

        # ── Llamar al LLM (PRO, 1-pass) ────────────────────────────
        logger.info(
            "B1: Comparing %d incidents (strategy=%s) for project %s",
            len(incidents),
            strategy,
            proyecto_id,
        )

        response = llm.run_agent(
            agent_id="incident_comparator",
            variables={
                "incidents_json": incidents_json,
                "strategy_note": strategy_note,
            },
        )

        # ── Persistir comparaciones ─────────────────────────────────
        comparisons = response.get("comparisons", [])
        comparisons_created = 0
        for comp in comparisons:
            try:
                session.execute(
                    text(
                        "INSERT INTO incident_comparisons "
                        "(id, incident_a_id, incident_b_id, proyecto_id, "
                        " similarity_score, are_interchangeable, rationale) "
                        "VALUES (gen_random_uuid(), :a_id, :b_id, :pid, "
                        " :score, :interchangeable, :rationale)"
                    ),
                    {
                        "a_id": comp["incident_a_id"],
                        "b_id": comp["incident_b_id"],
                        "pid": proyecto_id,
                        "score": comp.get("similarity_score", 0.0),
                        "interchangeable": comp.get("are_interchangeable", False),
                        "rationale": comp.get("rationale", ""),
                    },
                )
                comparisons_created += 1
            except Exception as e:
                logger.warning("B1: Failed to insert comparison: %s", e)

        # ── Persistir grupos ───────────────────────────────────────
        groups = response.get("groups", [])
        groups_created = 0
        groups_updated = 0
        for group in groups:
            incident_ids = group.get("incident_ids", [])
            if len(incident_ids) < 2:
                continue  # Grupo trivial

            # Ver si es merge con grupo existente (estrategia incremental)
            merge_target = group.get("merge_with_existing_group")

            if merge_target:
                # Agregar incidentes a grupo existente
                session.execute(
                    text(
                        "UPDATE incident_groups "
                        "SET incident_ids_json = incident_ids_json || :new_ids::jsonb "
                        "WHERE id = :gid AND proyecto_id = :pid"
                    ),
                    {
                        "new_ids": json.dumps(incident_ids),
                        "gid": merge_target,
                        "pid": proyecto_id,
                    },
                )
                groups_updated += 1
            else:
                # Nuevo grupo
                common_pattern = group.get("common_pattern", "")
                session.execute(
                    text(
                        "INSERT INTO incident_groups "
                        "(id, proyecto_id, label, definition, status, "
                        " incident_ids_json, labeled_by_agent) "
                        "VALUES (gen_random_uuid(), :pid, NULL, :pattern, 'open', "
                        " :ids::jsonb, NULL)"
                    ),
                    {
                        "pid": proyecto_id,
                        "pattern": common_pattern,
                        "ids": json.dumps(incident_ids),
                    },
                )
                groups_created += 1

        # ── Registrar ungrouped ─────────────────────────────────────
        ungrouped = response.get("ungrouped", [])
        ungrouped_count = len(ungrouped)
        if ungrouped:
            logger.info(
                "B1: %d ungrouped incidents for project %s",
                ungrouped_count,
                proyecto_id,
            )

        session.commit()

        logger.info(
            "B1 complete: %d comparisons, %d groups created, %d updated, %d ungrouped",
            comparisons_created,
            groups_created,
            groups_updated,
            ungrouped_count,
        )

        return {
            "comparisons_created": comparisons_created,
            "groups_created": groups_created,
            "groups_updated": groups_updated,
            "ungrouped_count": ungrouped_count,
            "strategy": strategy,
        }

    except Exception:
        session.rollback()
        logger.exception("B1 compare_incidents failed for project %s", proyecto_id)
        raise
    finally:
        session.close()
