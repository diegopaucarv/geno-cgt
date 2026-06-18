"""F2.5 — Core Pattern Verifier (PRO, every 3 documents).

Compares the last 3 individual patterns per document and evaluates
whether they converge toward a shared pattern. Triggers HITL gate
GATE_PATTERN_OF_INTEREST.
"""

from __future__ import annotations

import logging
import sys

sys.path.insert(0, "/app")
from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def verify_core_pattern(proyecto_id: str) -> dict:
    """Compare last 3 per-document patterns and evaluate convergence."""
    session = SessionLocal()
    try:
        # 1. Get last 3 document_processes with patterns
        rows = session.execute(
            text(
                "SELECT dp.process_description, dp.prime_mover, d.original_filename "
                "FROM document_processes dp JOIN documentos d ON d.id = dp.documento_id "
                "WHERE dp.proyecto_id = :pid AND dp.prime_mover IS NOT NULL "
                "ORDER BY dp.creado_en DESC LIMIT 3"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        if len(rows) < 3:
            return {
                "error": "insufficient_documents",
                "count": len(rows),
                "required": 3,
            }

        # 2. Build patterns text
        patterns_parts = []
        for i, row in enumerate(reversed(rows)):
            desc = row[0] or ""
            gerund = desc.split("\n")[0].strip() if desc else "(sin patron)"
            patterns_parts.append(
                f"--- Pattern {i + 1} (doc: {row[2]}) ---\nGerund: {gerund}\n{desc[:500]}"
            )
        patterns_text = "\n".join(patterns_parts)

        # 3. Get object_of_study and guidance
        oos_row = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # 4. Get population_context
        pop_row = session.execute(
            text(
                "SELECT surprising_details, language_patterns, data_production_context "
                "FROM population_contexts WHERE proyecto_id = :pid ORDER BY version DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        population_context = (
            "Surprising: " + (pop_row[0] or "N/A") if pop_row else "(none)"
        )

        # 5. Get operational_question
        pa_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa = pa_row[0] if pa_row and pa_row[0] else {}
        rq = pa.get("research_question", {}) if isinstance(pa, dict) else {}
        operational_question = rq.get("operational_question", "(not yet generated)")

        # 6. Call PRO agent
        result = llm.run_agent(
            "core_pattern_verifier",
            variables={
                "patterns": patterns_text[:8000],
                "population_context": population_context[:2000],
                "object_of_study": object_of_study,
                "operational_question": operational_question,
            },
        )

        # 7. Store HITL decision
        from app.agents.transitions import hitl_gate

        GATE_PATTERN_OF_INTEREST = "pattern_of_interest"

        proposal = {
            "convergence_assessment": result.get("convergence_assessment", ""),
            "converging": result.get("converging", []),
            "diverging": result.get("diverging", []),
            "recommendation": result.get("recommendation", "CONTINUE_COLLECTING"),
            "suggested_shared_pattern": result.get("suggested_shared_pattern", ""),
        }
        critic_verdict = {
            "confidence": result.get("confidence", "MEDIUM"),
            "population_concerns": result.get("population_concerns", []),
        }
        hitl_gate(
            session, proyecto_id, GATE_PATTERN_OF_INTEREST, proposal, critic_verdict
        )
        session.commit()

        return {**result, "hitl_status": "pending", "documents_compared": len(rows)}
    except Exception:
        logger.exception("verify_core_pattern failed for %s", proyecto_id)
        return {"error": "exception", "proyecto_id": proyecto_id}
    finally:
        session.close()
