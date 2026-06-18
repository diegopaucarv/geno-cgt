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
    """Group incidents by behavioral patterns. One PRO call per batch of documents.

    Groups incidents WITH document provenance so the AI can identify
    cross-document variations. Each incident includes its source document.
    Previous categories (with variation summaries) are included as context.
    """
    session = SessionLocal()
    try:
        # ── Load previous categories with variation summaries ──
        prev_cats = session.execute(
            text(
                "SELECT c.nombre, c.definicion, "
                "COALESCE(jsonb_array_length(ig.incident_ids_json), 0) as inc_count "
                "FROM categorias c "
                "LEFT JOIN incident_groups ig ON ig.label = c.nombre "
                "AND ig.proyecto_id = c.proyecto_id "
                "WHERE c.proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        previous_categories_text = ""
        if prev_cats:
            previous_categories_text = (
                "PREVIOUS CATEGORIES (from earlier batches):\n"
                + "\n".join(f"- {c[0]}: {c[1]} ({c[2]} incidents)" for c in prev_cats)
            )

        # ── Load incidents grouped by document ──
        rows = session.execute(
            text(
                "SELECT ei.id, ei.jot_text, ei.preguntas_glaser_json, "
                "d.original_filename "
                "FROM extracted_incidents ei "
                "JOIN documentos d ON ei.documento_id = d.id "
                "WHERE ei.proyecto_id = :pid "
                "ORDER BY d.original_filename, ei.creado_en"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        if len(rows) < 2:
            logger.info("B1: <2 incidents — nothing to group")
            return {"groups_created": 0, "incidents_grouped": 0}

        # ── Build incidents grouped by document ──
        inc_map = {}
        doc_blocks = []
        global_idx = 0
        current_doc = None
        current_block = []
        for r in rows:
            inc_id = str(r[0])
            desc = r[1] or ""
            meta = r[2] if isinstance(r[2], dict) else {}
            doc_name = r[3] or "unknown"
            global_idx += 1
            short_id = f"inc_{global_idx}"
            inc_map[short_id] = inc_id
            if doc_name != current_doc:
                if current_block:
                    doc_blocks.append((current_doc, current_block))
                current_doc = doc_name
                current_block = []
            current_block.append(
                {
                    "id": short_id,
                    "description": desc,
                }
            )
        if current_block:
            doc_blocks.append((current_doc, current_block))

        # ── Build the prompt text ──
        incidents_text = (
            previous_categories_text + "\n" if previous_categories_text else ""
        )
        for doc_name, incidents in doc_blocks:
            incidents_text += (
                f"\n=== Document: {doc_name} ({len(incidents)} incidents) ===\n"
            )
            for inc in incidents:
                incidents_text += f"[{inc['id']}] {inc['description']}\n"

        total_incidents = global_idx
        total_chars = len(incidents_text)
        logger.info(
            "B1: %d incidents across %d docs → %d chars",
            total_incidents,
            len(doc_blocks),
            total_chars,
        )

        # ── Get project config ──
        operational_question = _get_operational_question(session, proyecto_id)
        object_of_study = _get_object_of_study(session, proyecto_id)

        # ── Call AI (PRO) ──
        response = llm.run_agent(
            "fb_incident_grouper",
            variables={
                "incidents_json": incidents_text,
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
