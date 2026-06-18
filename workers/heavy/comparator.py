"""
B1 — Incident Grouper (PRO, 1-pass, AI-only).

Receives ALL incidents from a project and proposes groups based on
behavioral patterns (operational question patterns). NO pre-filter,
NO pairwise comparison, NO Union-Find. The AI does all the grouping.

Replaces the old comparator.py which used cosine pre-filter + pairwise
LLM comparison + Union-Find — three steps that accumulated errors.
"""

from __future__ import annotations

import json
import logging

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def _get_operational_question(session, proyecto_id: str) -> str:
    pa = session.execute(
        text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if pa and pa[0] and isinstance(pa[0], dict):
        rq = pa[0].get("research_question", {})
        return rq.get("operational_question", "") if isinstance(rq, dict) else ""
    return ""


def _get_object_of_study(session, proyecto_id: str) -> str:
    row = session.execute(
        text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    return row[0] if row and row[0] else "concern"


def b1_group_incidents(proyecto_id: str, incremental: bool = False) -> dict:
    """Send ALL incidents to the AI. AI proposes groups based on patterns.

    One PRO call. No pre-filter. No pairwise comparison.

    Returns:
        dict with groups_created, incidents_grouped.
    """
    session = SessionLocal()
    try:
        # ── Load all incidents with their segment_refs ──
        rows = session.execute(
            text(
                "SELECT ei.id, ei.jot_text, ei.preguntas_glaser_json "
                "FROM extracted_incidents ei "
                "WHERE ei.proyecto_id = :pid "
                "ORDER BY ei.creado_en"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        if len(rows) < 2:
            logger.info("B1: <2 incidents — nothing to group")
            return {"groups_created": 0, "incidents_grouped": 0}

        # ── Build incidents JSON for the AI ──
        # Use short stable IDs (inc_1, inc_2...) — LLMs can't copy UUIDs accurately
        inc_map = {}  # short_id → full UUID
        incidents_list = []
        for i, r in enumerate(rows):
            inc_id = str(r[0])
            short_id = f"inc_{i + 1}"
            inc_map[short_id] = inc_id
            desc = r[1] or ""
            meta = r[2] if isinstance(r[2], dict) else {}
            incidents_list.append(
                {
                    "id": short_id,
                    "description": desc,
                    "segment_refs": meta.get("segment_refs", []),
                    "patterns": meta.get("patterns", []),
                }
            )

        incidents_json = json.dumps(incidents_list, ensure_ascii=False)
        logger.info(
            "B1: %d incidents → sending to AI grouper (%d chars)",
            len(rows),
            len(incidents_json),
        )

        # ── Get project config ──
        operational_question = _get_operational_question(session, proyecto_id)
        object_of_study = _get_object_of_study(session, proyecto_id)

        # ── Call AI (PRO) ──
        response = llm.run_agent(
            "fb_incident_grouper",
            variables={
                "incidents_json": incidents_json,
                "operational_question": operational_question or "(not yet generated)",
                "object_of_study": object_of_study,
            },
        )

        # ── Debug empty responses ──
        groups = response.get("groups", [])
        if not groups:
            logger.warning(
                "B1: 0 groups in AI response. Keys: %s, raw (500 chars): %s",
                list(response.keys())
                if isinstance(response, dict)
                else type(response).__name__,
                str(response)[:500],
            )
            return {"groups_created": 0, "incidents_grouped": 0}

        # ── Persist groups ──
        groups_created = 0
        incidents_grouped = 0

        # Delete old groups for this project (idempotent re-run)
        session.execute(
            text("DELETE FROM incident_groups WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        )

        for g in groups:
            signal = g.get("signal", "").strip()
            incident_ids = g.get("incident_ids", [])
            rationale = g.get("rationale", "")

            if not signal or len(incident_ids) < 2:
                continue

            # Validate incident IDs — resolve short IDs back to UUIDs
            valid_ids = []
            for iid in incident_ids:
                # Try short ID first (inc_1, inc_2...)
                real_id = inc_map.get(iid)
                if real_id:
                    valid_ids.append(real_id)
                else:
                    # Fallback: direct UUID lookup
                    exists = session.execute(
                        text(
                            "SELECT 1 FROM extracted_incidents "
                            "WHERE id::text LIKE :prefix AND proyecto_id = :pid"
                        ),
                        {"prefix": f"{iid[:8]}%", "pid": proyecto_id},
                    ).fetchone()
                    if exists:
                        valid_ids.append(iid)

            if len(valid_ids) < 2:
                continue

            session.execute(
                text(
                    "INSERT INTO incident_groups "
                    "(id, proyecto_id, label, definition, status, incident_ids_json) "
                    "VALUES (gen_random_uuid(), :pid, :label, :def, 'open', "
                    "CAST(:ids AS jsonb))"
                ),
                {
                    "pid": proyecto_id,
                    "label": signal,
                    "def": rationale,
                    "ids": json.dumps(valid_ids),
                },
            )
            groups_created += 1
            incidents_grouped += len(valid_ids)

        session.commit()

        logger.info(
            "B1 complete: %d groups, %d incidents grouped (from %d total)",
            groups_created,
            incidents_grouped,
            len(rows),
        )

        return {
            "groups_created": groups_created,
            "incidents_grouped": incidents_grouped,
            "total_incidents": len(rows),
        }

    except Exception:
        session.rollback()
        logger.exception("B1 group_incidents failed for project %s", proyecto_id)
        raise
    finally:
        session.close()
