"""F6e — Final Report Generator (PRO, terminal node).

Generates the complete theoretical report integrating all phases.
This is a PROPOSER agent. The researcher reviews via HITL.
"""

from __future__ import annotations

import json
import logging
import sys

sys.path.insert(0, "/app")
from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def generate_final_report(proyecto_id: str) -> dict:
    """Generate complete final theoretical report (PRO, terminal node)."""
    session = SessionLocal()
    try:
        # Gather all study data
        proj = session.execute(
            text(
                "SELECT object_of_study, population_assumption FROM proyectos WHERE id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        if not proj:
            return {"error": "project_not_found"}

        object_of_study = proj[0] or "concern"
        pa = proj[1] or {}
        rq_data = pa.get("research_question", {}) if isinstance(pa, dict) else {}
        research_question = rq_data.get("research_question", "(not generated)")
        population_description = pa.get("population_description", "(not specified)")

        # Core concern from HITL
        cc = session.execute(
            text(
                "SELECT proposal->>'core_concern' FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'pattern_of_interest' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        core_concern = cc[0] if cc and cc[0] else "(not identified)"

        # Core category from HITL
        core_cat_row = session.execute(
            text(
                "SELECT proposal FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'core_emergence' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        core_category = "(not identified)"
        if core_cat_row and core_cat_row[0]:
            cat_proposal = (
                core_cat_row[0]
                if isinstance(core_cat_row[0], dict)
                else json.loads(core_cat_row[0])
            )
            candidates = cat_proposal.get("core_category_candidates", [])
            if candidates:
                core_category = candidates[0].get(
                    "code_name", candidates[0].get("code_label", "(unnamed)")
                )

        # Nodes and edges
        nodes_text = _get_nodes_text(session, proyecto_id)
        edges_text = _get_edges_text(session, proyecto_id)

        # Hypotheses
        hyps = session.execute(
            text(
                "SELECT statement FROM hypotheses WHERE proyecto_id = :pid AND status = 'confirmed'"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        hypotheses = "\n".join(f"- {h[0]}" for h in hyps) if hyps else "(none)"

        # Literature
        try:
            lit = session.execute(
                text(
                    "SELECT comparison_table FROM literature_dialogues WHERE proyecto_id = :pid ORDER BY creado_en DESC LIMIT 1"
                ),
                {"pid": proyecto_id},
            ).fetchone()
            literature_dialogue = (
                json.dumps(lit[0], ensure_ascii=False)
                if lit and lit[0]
                else "(not performed)"
            )
        except Exception:
            literature_dialogue = "(literature table not available)"

        # Applicability
        try:
            app = session.execute(
                text(
                    "SELECT guidelines FROM applicability_guidelines WHERE proyecto_id = :pid ORDER BY creado_en DESC LIMIT 1"
                ),
                {"pid": proyecto_id},
            ).fetchone()
            applicability_guidelines = (
                json.dumps(app[0], ensure_ascii=False)
                if app and app[0]
                else "(not generated)"
            )
        except Exception:
            applicability_guidelines = "(applicability table not available)"

        # Call PRO agent
        result = llm.run_agent(
            "final_report",
            variables={
                "object_of_study": object_of_study,
                "research_question": research_question,
                "core_concern": core_concern,
                "core_category": core_category,
                "nodes": nodes_text,
                "edges": edges_text,
                "hypotheses": hypotheses,
                "population_description": population_description,
                "literature_dialogue": literature_dialogue,
                "applicability_guidelines": applicability_guidelines,
                "Pattern": object_of_study,
                "processing_verb": pa.get("processing_verb", "resolve"),
                "processing_gerund": pa.get("processing_gerund", "resolving"),
            },
            max_tokens=8000,
            temperature=0.3,
        )

        # Store in final_reports table (create if not exists)
        try:
            session.execute(
                text(
                    "INSERT INTO final_reports (id, proyecto_id, content, creado_en) "
                    "VALUES (gen_random_uuid(), :pid, :content, NOW()) "
                    "ON CONFLICT (proyecto_id) DO UPDATE SET content = :content2, actualizado_en = NOW()"
                ),
                {
                    "pid": proyecto_id,
                    "content": json.dumps(result, ensure_ascii=False),
                    "content2": json.dumps(result, ensure_ascii=False),
                },
            )
            session.commit()
        except Exception:
            logger.warning(
                "final_reports table not available — report will not be persisted"
            )

        return {"status": "completed", "proyecto_id": proyecto_id, "report": result}
    except Exception:
        logger.exception("generate_final_report failed for %s", proyecto_id)
        return {"error": "exception", "proyecto_id": proyecto_id}
    finally:
        session.close()


def _get_nodes_text(session, proyecto_id: str) -> str:
    try:
        rows = session.execute(
            text(
                "SELECT label, entity_type, definition FROM database_nodes WHERE project_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        return (
            "\n".join(f"- [{r[1]}] {r[0]}: {r[2]}" for r in rows)
            if rows
            else "(no nodes)"
        )
    except Exception:
        return "(nodes table not available)"


def _get_edges_text(session, proyecto_id: str) -> str:
    try:
        rows = session.execute(
            text(
                "SELECT src.label, e.relationship_type, tgt.label, "
                "COALESCE(e.evidence, '') as evidence "
                "FROM database_edges e "
                "JOIN database_nodes src ON e.source_node_id = src.id "
                "JOIN database_nodes tgt ON e.target_node_id = tgt.id "
                "WHERE e.project_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        return (
            "\n".join(f"- {r[0]} --[{r[1]}]--> {r[2]}: {r[3]}" for r in rows)
            if rows
            else "(no edges)"
        )
    except Exception:
        return "(edges table not available)"
