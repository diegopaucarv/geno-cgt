"""F2.5 — Core Pattern Verifier (PRO, every 3 documents).

Compares the last 3 individual patterns per document and evaluates
whether they converge toward a shared pattern. Triggers HITL gate
GATE_PATTERN_CONVERGENCE ("pattern_convergence"), which is distinct from the
main-concern gate GATE_PATTERN_OF_INTEREST: reusing the latter made the
frontend render this convergence payload as an empty concern proposal.
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, "/app")
from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def verify_core_pattern(proyecto_id: str) -> dict:
    """Compare the last N per-document patterns and evaluate convergence."""
    try:
        batch_size = max(1, int(os.getenv("GT_OPEN_CODING_BATCH_SIZE", "3")))
    except (TypeError, ValueError):
        batch_size = 3
    session = SessionLocal()
    try:
        # 1. Get the last `batch_size` document_processes with patterns
        rows = session.execute(
            text(
                "SELECT dp.process_description, dp.prime_mover, d.original_filename "
                "FROM document_processes dp JOIN documentos d ON d.id = dp.documento_id "
                "WHERE dp.proyecto_id = :pid AND dp.prime_mover IS NOT NULL "
                "ORDER BY dp.creado_en DESC LIMIT :lim"
            ),
            {"pid": proyecto_id, "lim": batch_size},
        ).fetchall()

        if len(rows) < batch_size:
            return {
                "error": "insufficient_documents",
                "count": len(rows),
                "required": batch_size,
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
        research_question = rq.get("research_question", "(not yet generated)")
        processing_verb = (
            pa.get("processing_verb", "resolve") if isinstance(pa, dict) else "resolve"
        )
        processing_gerund = (
            pa.get("processing_gerund", "resolving")
            if isinstance(pa, dict)
            else "resolving"
        )

        # 5b. Get coding_style_instruction (G21)
        coding_style_instruction = (
            pa.get("coding_style_instruction", "") if isinstance(pa, dict) else ""
        )
        if not coding_style_instruction:
            from app.core.coding_styles import get_default_style_instruction

            coding_style_instruction = get_default_style_instruction()

        # 6. Call PRO agent
        result = llm.run_agent(
            "fa_core_pattern_verifier",
            variables={
                "patterns": patterns_text[:8000],
                "population_context": population_context[:2000],
                "object_of_study": object_of_study,
                "operational_question": operational_question,
                "research_question": research_question,
                "coding_style_instruction": coding_style_instruction,
                "processing_verb": processing_verb,
                "processing_gerund": processing_gerund,
            },
        )

        # 6b. Progreso del lote, para que el modal pueda decir
        # "N de M documentos procesados. ¿Continuar?".
        #
        # `docs_processed` usa EL MISMO predicado que la frontera del lote en
        # `tasks.py` (`prime_mover_confidence IS NOT NULL`). Contar por
        # `documentos.estado` daba N-1: el gate se despacha ANTES de que el
        # documento en curso pase a `incidentes_extraidos`.
        #
        # `rollback()` antes de volver a tocar la DB: la transacción quedó
        # ociosa durante toda la llamada PRO (decenas de segundos) y una
        # conexión cortada aquí haría que el gate no se cree nunca.
        session.rollback()
        docs_processed = session.execute(
            text(
                "SELECT COUNT(*) FROM document_processes "
                "WHERE proyecto_id = :pid AND prime_mover_confidence IS NOT NULL"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]
        # El total excluye documentos en `error`: nunca podrían extraerse y
        # dejarían el contador sin llegar a M.
        total_docs = session.execute(
            text(
                "SELECT COUNT(*) FROM documentos "
                "WHERE proyecto_id = :pid AND TRIM(estado) <> 'error'"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        # 7. Store HITL decision
        from app.agents.transitions import GATE_PATTERN_CONVERGENCE, hitl_gate

        proposal = {
            "convergence_assessment": result.get("convergence_assessment", ""),
            "converging": result.get("converging", []),
            "diverging": result.get("diverging", []),
            "recommendation": result.get("recommendation", "CONTINUE_COLLECTING"),
            "suggested_shared_pattern": result.get("suggested_shared_pattern", ""),
            "docs_processed": docs_processed,
            "total_docs": total_docs,
            "batch_size": batch_size,
        }
        critic_verdict = {
            "confidence": result.get("confidence", "MEDIUM"),
            "population_concerns": result.get("population_concerns", []),
        }
        hitl_gate(
            session,
            proyecto_id,
            GATE_PATTERN_CONVERGENCE,
            proposal,
            critic_verdict,
        )
        session.commit()

        return {**result, "hitl_status": "pending", "documents_compared": len(rows)}
    except Exception:
        logger.exception("verify_core_pattern failed for %s", proyecto_id)
        return {"error": "exception", "proyecto_id": proyecto_id}
    finally:
        session.close()
