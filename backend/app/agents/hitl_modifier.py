"""HITLModificationAgent: P5 — Modificacion de Memos con Verificacion Agencial.

Orquesta 5 fases:
  1. FLASH filter: clasifica pedido como valido/invalido
  2. PRO planner: rewordea + plan de verificacion + hipotesis de falseacion
  3. EXECUTION: ReactRunner ejecuta el plan con tools
  4. PRO evaluator: decide si el cambio es recomendable
  5. APPLY: (opcional, solo si usuario confirma) modifica + wipea + reinicia

Depende de:
  - agent_families (tabla de referencia en DB, ya seedeada)
  - ReactRunner + ToolRegistry (ya construidos)
  - prompts P5 (hitl_modification_filter/hitl_modification_planner/hitl_modification_evaluator/hitl_evidence_collector)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import AgentResult
from app.agents.react_runner import ReactRunner
from app.agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# CHANGE_IMPACT_MAP
# ═══════════════════════════════════════════════════════════════════════

CHANGE_IMPACT_MAP: dict[str, dict[str, Any]] = {
    # ── Inductiva a DATOS ───────────────────────────────────────────
    "batch_coder_producer": {
        "output_table": "categorias",
        "output_field": "definicion",
        "dependent_tables": [
            "codigos_segmento",
            "code_document_summaries",
            "code_global_summaries",
        ],
        "invalidates": [
            "B2.5 grounding",
            "B3 hypotheses",
            "util_map_synthesis",
            "util_reduce_synthesis",
        ],
        "restart_from": "batch_code",
    },
    "b2b_generate_codes": {
        "output_table": "categorias",
        "output_field": "definicion",
        "dependent_tables": [
            "codigos_segmento",
            "code_document_summaries",
            "code_global_summaries",
        ],
        "invalidates": ["B2.5 grounding", "B3 hypotheses", "util_map_synthesis"],
        "restart_from": "batch_code",
    },
    "incident_extractor": {
        "output_table": "categorias",
        "output_field": "definicion",
        "dependent_tables": [],
        "invalidates": ["incidentes extraidos de esta categoria"],
        "restart_from": "batch_code",
    },
    # ── Inductiva a CONCEPTOS ──────────────────────────────────────
    "main_concern_proposer": {
        "output_table": "proyectos",
        "output_field": "supuesto_poblacional",
        "dependent_tables": ["hypotheses", "conceptual_relationships"],
        "invalidates": ["B3 hypotheses", "selective_coding", "theoretical_playground"],
        "restart_from": "find_core_concern",
    },
    "b3_hypothesis_generator": {
        "output_table": "hypotheses",
        "output_field": "text",
        "dependent_tables": ["conceptual_relationships", "elaboration_memos"],
        "invalidates": ["selective_coding", "theoretical_playground"],
        "restart_from": "generate_hypotheses",
    },
    "react_hypothesis": {
        "output_table": "hypotheses",
        "output_field": "text",
        "dependent_tables": ["conceptual_relationships", "elaboration_memos"],
        "invalidates": ["selective_coding", "theoretical_playground"],
        "restart_from": "generate_hypotheses",
    },
    # ── Descriptiva a DATOS ────────────────────────────────────────
    "a1_population_context": {
        "output_table": "population_contexts",
        "output_field": "surprising_details",
        "dependent_tables": [],
        "invalidates": ["A2 process_identifier (pierde contexto comparativo)"],
        "restart_from": "segment_and_index",
    },
    "a2_process_identifier": {
        "output_table": "document_processes",
        "output_field": "process_description",
        "dependent_tables": ["hypotheses"],
        "invalidates": ["A3 sense_maker", "B1 sampling", "B3 hypotheses"],
        "restart_from": "segment_and_index",
    },
    "b1_sampling_distiller": {
        "output_table": None,
        "output_field": None,
        "dependent_tables": [],
        "invalidates": ["criterios de muestreo teorico derivados"],
        "restart_from": "batch_code",
    },
    "util_map_synthesis": {
        "output_table": "code_document_summaries",
        "output_field": "summary",
        "dependent_tables": ["code_global_summaries"],
        "invalidates": ["util_reduce_synthesis"],
        "restart_from": "map_synthesize",
    },
    "util_reduce_synthesis": {
        "output_table": "code_global_summaries",
        "output_field": "summary",
        "dependent_tables": [],
        "invalidates": ["definicion consolidada del codigo"],
        "restart_from": "reduce_synthesize",
    },
    # ── Evaluativa / Critica ───────────────────────────────────────
    "batch_coder_critic": {
        "output_table": None,
        "output_field": None,
        "dependent_tables": ["categorias"],
        "invalidates": ["codigos aceptados/rechazados"],
        "restart_from": "batch_code",
    },
    # ── Estructural / Transformacional ─────────────────────────────
    "database_a_proposer": {
        "output_table": "conceptual_relationships",
        "output_field": "category_ids",
        "dependent_tables": ["elaboration_memos", "ecosystem_layouts"],
        "invalidates": ["theoretical_playground completo"],
        "restart_from": "prepare_playground",
    },
    # ── Elaborativa ────────────────────────────────────────────────
    "f6b_conceptual_elaborator": {
        "output_table": "conceptual_relationships",
        "output_field": "elaboration_status",
        "dependent_tables": ["elaboration_memos"],
        "invalidates": ["relaciones derivadas", "recommendation_engine"],
        "restart_from": "prepare_playground",
    },
    "core_saturation_proposer": {
        "output_table": "saturation_metrics",
        "output_field": "saturation_status",
        "dependent_tables": [],
        "invalidates": ["metricas de saturacion del codigo"],
        "restart_from": "calculate_saturation",
    },
    "f6b_ghost_blob_mapper": {
        "output_table": None,
        "output_field": None,
        "dependent_tables": ["elaboration_memos"],
        "invalidates": ["mapeo memos → categorias"],
        "restart_from": "prepare_playground",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ModificationResult:
    """Resultado unificado del P5 Modification Agent."""

    valid_request: bool
    filter_reason: str = ""
    suggested_questions: list[str] = field(default_factory=list)

    recommended: bool | None = None
    recommendation_reason: str = ""
    recommendation_confidence: float = 0.0

    evidence_sufficient: bool = False
    evidence_collected: list[dict[str, Any]] = field(default_factory=list)
    verification_plan: dict[str, Any] | None = None
    rewritten_request: str = ""
    falsification_hypothesis: str = ""

    modified_memo: dict[str, Any] | None = None
    impact_summary: str = ""
    missing_evidence: str = ""

    applied: bool = False
    wiped_tables: list[str] = field(default_factory=list)
    pipeline_restarted_from: str = ""

    error: str | None = None

    def to_response(self) -> dict[str, Any]:
        """Formato para la respuesta de API."""
        return {
            "valid_request": self.valid_request,
            "filter_reason": self.filter_reason,
            "suggested_questions": self.suggested_questions,
            "recommended": self.recommended,
            "recommendation_reason": self.recommendation_reason,
            "recommendation_confidence": self.recommendation_confidence,
            "evidence_sufficient": self.evidence_sufficient,
            "modified_memo": self.modified_memo,
            "impact_summary": self.impact_summary,
            "missing_evidence": self.missing_evidence or None,
            "applied": self.applied,
            "wiped_tables": self.wiped_tables,
            "pipeline_restarted_from": self.pipeline_restarted_from or None,
            "error": self.error,
        }


# ═══════════════════════════════════════════════════════════════════════
# HITLModificationAgent
# ═══════════════════════════════════════════════════════════════════════


class HITLModificationAgent:
    """Orquesta las 5 fases del P5: filtro → plan → ejecucion → evaluacion → apply."""

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    # ── Public API ────────────────────────────────────────────────

    def process_request(
        self,
        agent_id: str,
        user_request: str,
        current_memo: dict[str, Any],
        proyecto_id: str,
        original_prompt: str = "",
    ) -> ModificationResult:
        """Procesa un pedido de modificacion completo (Fases 1-4).

        La Fase 5 (apply) se ejecuta por separado si el usuario confirma.
        """
        try:
            # ── Fase 1: FLASH filter ──────────────────────────────
            filter_result = self._phase1_filter(agent_id, user_request)
            if not filter_result.valid_request:
                return filter_result

            # ── Fase 2: PRO planner ───────────────────────────────
            plan = self._phase2_plan(
                agent_id, user_request, current_memo, proyecto_id, original_prompt
            )
            if plan.error:
                return plan

            # ── Fase 3: Execution ─────────────────────────────────
            plan.evidence_collected = self._phase3_execute(
                plan.verification_plan or {}, proyecto_id, agent_id
            )

            # ── Fase 4: PRO evaluator ─────────────────────────────
            result = self._phase4_evaluate(agent_id, current_memo, plan)
            result.valid_request = True
            result.filter_reason = filter_result.filter_reason
            return result

        except Exception as e:
            logger.error("HITLModificationAgent failed: %s", e)
            return ModificationResult(valid_request=False, error=str(e))

    def apply_modification(
        self,
        agent_id: str,
        memo_id: str,
        new_content: dict[str, Any],
        proyecto_id: str,
    ) -> dict[str, Any]:
        """Fase 5: Aplica la modificacion confirmada por el usuario."""
        impact = CHANGE_IMPACT_MAP.get(agent_id, {})

        try:
            wiped: list[str] = []
            table = impact.get("output_table")
            field = impact.get("output_field")

            if table and field and memo_id:
                self._update_output(table, field, memo_id, new_content)

            for dep_table in impact.get("dependent_tables", []):
                self._wipe_table(dep_table, proyecto_id)
                wiped.append(dep_table)

            restart_from = impact.get("restart_from", "")
            if restart_from:
                self._restart_pipeline(proyecto_id, restart_from)

            return {
                "status": "applied",
                "wiped_tables": wiped,
                "restart_from": restart_from,
                "invalidated_outputs": impact.get("invalidates", []),
            }
        except Exception as e:
            logger.error("apply_modification failed: %s", e)
            return {"status": "error", "error": str(e)}

    # ── Phase 1: FLASH Filter ─────────────────────────────────────

    def _phase1_filter(self, agent_id: str, user_request: str) -> ModificationResult:
        """Clasifica el pedido como valido/invalido usando FLASH."""
        family_data = self._load_family_data(agent_id)
        if not family_data:
            return ModificationResult(
                valid_request=False,
                filter_reason=f"Agente '{agent_id}' no encontrado en agent_families.",
            )

        response = self.llm.run_agent(
            "hitl_modification_filter",
            variables={
                "agent_id": agent_id,
                "agent_family": family_data["family"],
                "family_label": family_data["label"],
                "family_research_question": family_data["research_question"],
                "accepted_questions": json.dumps(
                    family_data.get("accepted_questions", []), ensure_ascii=False
                ),
                "rejected_questions": json.dumps(
                    family_data.get("rejected_questions", []), ensure_ascii=False
                ),
                "user_request": user_request,
            },
            temperature=0.1,
        )

        valid = response.get("valid", False)
        return ModificationResult(
            valid_request=valid,
            filter_reason=response.get("reason", ""),
            suggested_questions=response.get("suggested_questions", []),
        )

    # ── Phase 2: PRO Planner ──────────────────────────────────────

    def _phase2_plan(
        self,
        agent_id: str,
        user_request: str,
        current_memo: dict[str, Any],
        proyecto_id: str,
        original_prompt: str,
    ) -> ModificationResult:
        """PRO planifica la verificacion del pedido."""
        family_data = self._load_family_data(agent_id) or {}
        impact = CHANGE_IMPACT_MAP.get(agent_id, {})

        response = self.llm.run_agent(
            "hitl_modification_planner",
            variables={
                "agent_family": family_data.get("family", ""),
                "family_research_question": family_data.get("research_question", ""),
                "family_verification_method": family_data.get(
                    "verification_method", ""
                ),
                "original_prompt": original_prompt or "(no disponible)",
                "current_memo": json.dumps(current_memo, ensure_ascii=False),
                "change_impact": json.dumps(impact, ensure_ascii=False),
                "user_request": user_request,
            },
            temperature=0.3,
        )

        return ModificationResult(
            valid_request=True,
            rewritten_request=response.get("rewritten_request", ""),
            verification_plan=response.get("verification_plan", {}),
            falsification_hypothesis=response.get("falsification_hypothesis", ""),
        )

    # ── Phase 3: Execution ────────────────────────────────────────

    def _phase3_execute(
        self,
        verification_plan: dict[str, Any],
        proyecto_id: str,
        agent_id: str,
    ) -> list[dict[str, Any]]:
        """Ejecuta el plan con ReactRunner + tools."""
        family_data = self._load_family_data(agent_id) or {}
        agent_family = family_data.get("family", "unknown")

        # Configurar tools
        from app.agents.tools.compare_tools import (
            compare_embeddings,
            find_similar_codes,
        )
        from app.agents.tools.db_tools import get_code_details
        from app.agents.tools.search_tools import search_segments

        tools = ToolRegistry()
        tools.register(
            search_segments, "search_segments", "Busca segmentos semanticamente."
        )
        tools.register(
            get_code_details,
            "get_code_details",
            "Definicion + incidentes de un codigo.",
        )
        tools.register(
            compare_embeddings, "compare_embeddings", "Similitud entre dos textos."
        )
        tools.register(
            find_similar_codes, "find_similar_codes", "Detecta codigos redundantes."
        )
        tools.register(
            lambda step, pid, fam: self._search_evidence(step, pid, fam),
            "search_evidence_for_modification",
            "Busca evidencia guiada por FLASH.",
            {
                "plan_step": "descripcion",
                "proyecto_id": "UUID",
                "agent_family": "familia",
            },
        )

        runner = ReactRunner(
            agent_id="hitl_modification_executor",
            llm_client=self.llm,
            tool_registry=tools,
            max_iterations=len(verification_plan.get("steps", [])) + 2,
            timeout_seconds=120.0,
        )

        result = runner.run(
            project_id=proyecto_id,
            role_description=(
                f"Ejecuta el plan de verificacion paso a paso. "
                f"Familia del agente: {agent_family}. "
                f"Plan: {json.dumps(verification_plan, ensure_ascii=False)[:2000]}"
            ),
        )

        if result.success:
            return (
                result.data.get("results", result.data)
                if isinstance(result.data, dict)
                else []
            )

        logger.warning("Phase 3 execution failed: %s", result.error)
        return []

    def _search_evidence(
        self, plan_step: str, proyecto_id: str, agent_family: str
    ) -> dict[str, Any]:
        """Tool: busqueda de evidencia guiada por FLASH."""
        queries_response = self.llm.run_agent(
            "hitl_evidence_collector",
            variables={
                "plan_step": plan_step,
                "agent_family": agent_family,
            },
            temperature=0.2,
        )

        results: list[dict[str, Any]] = []
        for query in queries_response.get("queries", []):
            qtype = query.get("type", "")
            try:
                if qtype == "rag":
                    from app.agents.tools.search_tools import search_segments

                    segments = search_segments(
                        query.get("text", plan_step), proyecto_id, top_k=5
                    )
                    results.append(
                        {"source": "rag", "query": query, "results": segments}
                    )
                elif qtype == "code_lookup":
                    from app.agents.tools.db_tools import get_code_details

                    details = get_code_details(query.get("code_id", ""))
                    results.append({"source": "db", "query": query, "results": details})
                elif qtype == "compare":
                    from app.agents.tools.compare_tools import compare_embeddings

                    sim = compare_embeddings(
                        query.get("text_a", ""), query.get("text_b", "")
                    )
                    results.append({"source": "tei", "query": query, "results": sim})
                elif qtype == "similar_codes":
                    from app.agents.tools.compare_tools import find_similar_codes

                    sim_codes = find_similar_codes(
                        query.get("code_definition", ""), proyecto_id
                    )
                    results.append(
                        {"source": "db", "query": query, "results": sim_codes}
                    )
            except Exception as e:
                logger.warning("Evidence query failed (%s): %s", qtype, e)
                results.append({"source": "error", "query": query, "error": str(e)})

        return {"evidence": results}

    # ── Phase 4: PRO Evaluator ────────────────────────────────────

    def _phase4_evaluate(
        self,
        agent_id: str,
        current_memo: dict[str, Any],
        plan_result: ModificationResult,
    ) -> ModificationResult:
        """PRO evalua si la modificacion es recomendable."""
        family_data = self._load_family_data(agent_id) or {}

        response = self.llm.run_agent(
            "hitl_modification_evaluator",
            variables={
                "agent_family": family_data.get("family", ""),
                "family_verification_method": family_data.get(
                    "verification_method", ""
                ),
                "current_memo": json.dumps(current_memo, ensure_ascii=False),
                "rewritten_request": plan_result.rewritten_request,
                "falsification_hypothesis": plan_result.falsification_hypothesis,
                "evidence": json.dumps(
                    plan_result.evidence_collected, ensure_ascii=False
                ),
            },
            temperature=0.3,
        )

        return ModificationResult(
            valid_request=True,
            recommended=response.get("recommended"),
            recommendation_reason=response.get("reason", ""),
            recommendation_confidence=response.get("confidence", 0.0),
            evidence_sufficient=response.get("evidence_sufficient", False),
            modified_memo=response.get("modified_memo"),
            impact_summary=response.get("impact_summary", ""),
            missing_evidence=response.get("missing_evidence", ""),
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _load_family_data(self, agent_id: str) -> dict[str, Any] | None:
        """Carga los datos de la familia desde agent_families + CHANGE_IMPACT_MAP."""
        import sys as _sys

        _sys.path.insert(0, "/app")
        from database import SessionLocal
        from sqlalchemy import text

        s = SessionLocal()
        try:
            row = s.execute(
                text(
                    "SELECT family, label, icon, description, research_question, "
                    "verification_method, accepted_questions, rejected_questions, "
                    "recommended_tools FROM agent_families "
                    "WHERE family = ("
                    "  SELECT CASE "
                    "    WHEN :aid IN ('b2b_generate_codes','batch_coder_producer','incident_extractor','prime_mover_extractor','definition_writer') "
                    "      THEN 'inductive_data'"
                    "    WHEN :aid2 IN ('main_concern_proposer','b3_hypothesis_generator','react_hypothesis','fc_core_category_proposer','selective_reduction_proposer','agrupador','a3_sense_maker') "
                    "      THEN 'inductive_concepts'"
                    "    WHEN :aid3 IN ('a1_population_context','a2_process_identifier','b1_sampling_distiller','util_map_synthesis','util_reduce_synthesis','f6a_final_report') "
                    "      THEN 'descriptive_data'"
                    "    WHEN :aid4 IN ('batch_coder_critic','main_concern_critic','core_emergence_critic','selective_reduction_critic','b2_critic','util_recategorization_decider') "
                    "      THEN 'evaluative'"
                    "    WHEN :aid5 IN ('database_a_proposer','database_b_proposer','database_a_critic','database_b_critic') "
                    "      THEN 'structural'"
                    "    ELSE 'elaborative'"
                    "  END"
                    ")"
                ),
                {
                    "aid": agent_id,
                    "aid2": agent_id,
                    "aid3": agent_id,
                    "aid4": agent_id,
                    "aid5": agent_id,
                },
            ).fetchone()

            if not row:
                return None

            return {
                "family": row[0],
                "label": row[1],
                "icon": row[2],
                "description": row[3],
                "research_question": row[4],
                "verification_method": row[5],
                "accepted_questions": row[6]
                if isinstance(row[6], list)
                else json.loads(row[6]),
                "rejected_questions": row[7]
                if isinstance(row[7], list)
                else json.loads(row[7]),
                "recommended_tools": row[8]
                if isinstance(row[8], list)
                else json.loads(row[8]),
            }
        finally:
            s.close()

    def _update_output(
        self, table: str, field: str, memo_id: str, new_content: dict[str, Any]
    ) -> None:
        """Actualiza una fila en una tabla de output."""
        import sys as _sys

        _sys.path.insert(0, "/app")
        from database import SessionLocal
        from sqlalchemy import text

        s = SessionLocal()
        try:
            value = (
                new_content.get(field)
                or new_content.get("definition")
                or new_content.get("text")
                or json.dumps(new_content, ensure_ascii=False)
            )
            s.execute(
                text(f"UPDATE {table} SET {field} = :val WHERE id = :mid"),
                {"val": value, "mid": memo_id},
            )
            s.commit()
            logger.info("Updated %s.%s for id=%s", table, field, memo_id)
        finally:
            s.close()

    def _wipe_table(self, table: str, proyecto_id: str) -> None:
        """Limpia una tabla dependiente para un proyecto."""
        import sys as _sys

        _sys.path.insert(0, "/app")
        from database import SessionLocal
        from sqlalchemy import text

        s = SessionLocal()
        try:
            s.execute(
                text(f"DELETE FROM {table} WHERE proyecto_id = :pid"),
                {"pid": proyecto_id},
            )
            s.commit()
            logger.info("Wiped %s for project %s", table, proyecto_id[:8])
        finally:
            s.close()

    def _restart_pipeline(self, proyecto_id: str, restart_from: str) -> None:
        """Dispara el reinicio del pipeline desde un checkpoint."""
        import os as _os

        try:
            from celery import Celery

            app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))
            app.send_task(
                "process_synthesis_agents_b",
                args=[proyecto_id],
                queue="heavy",
            )
            logger.info(
                "Pipeline restarted for %s from %s", proyecto_id[:8], restart_from
            )
        except Exception as e:
            logger.warning("Pipeline restart failed: %s", e)
