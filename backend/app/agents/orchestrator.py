"""OrchestratorAgent: motor de reglas deterministico para el pipeline.

Reemplaza llamadas LLM (~$0.0004 c/u) por una tabla de reglas.
90% de las decisiones son determinísticas. Los 2 casos ambiguos
se resuelven con heuristicas simples. Solo como ultimo recurso
se cae en LLM (FLASH, no PRO).

Basado en O2 del plan de optimizaciones.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Nodos del grafo LangGraph ─────────────────────────────────────
VALID_NODES: list[str] = [
    "segment_and_index",
    "extract_entities",
    "batch_code",
    "map_synthesize",
    "reduce_synthesize",
    "find_core_concern",
    "generate_hypotheses",
    "calculate_saturation",
    "theosampler_evaluate",
    "hitl_gap_review",
    "process_new_data",
    "prepare_playground",
    "hitl_review",
    "final_report",
]

# ── Reglas deterministicas (current_step → next_step) ────────────
# Cubre ~90% de las transiciones del pipeline.
RULES: dict[str, str] = {
    "segment_and_index": "extract_entities",
    "extract_entities": "batch_code",
    "batch_code": "map_synthesize",
    "map_synthesize": "reduce_synthesize",
    # "reduce_synthesize" → AMBIGUO: _resolve_after_reduce()
    "find_core_concern": "generate_hypotheses",
    "generate_hypotheses": "calculate_saturation",
    "calculate_saturation": "theosampler_evaluate",
    # "theosampler_evaluate" → AMBIGUO: _resolve_after_theosampler()
    "hitl_gap_review": "process_new_data",
    "process_new_data": "theosampler_evaluate",
    "prepare_playground": "hitl_review",
    "hitl_review": "final_report",
}


class OrchestratorRuleEngine:
    """Motor de reglas deterministico para decidir el proximo paso del pipeline.

    Attributes:
        llm: Cliente LLM opcional para fallback en casos no cubiertos.
    """

    def __init__(self, llm_client: Any | None = None):
        self.llm = llm_client

    # ── Public API ────────────────────────────────────────────────

    def decide(self, current_step: str, state: dict[str, Any]) -> str:
        """Decide el proximo nodo del pipeline.

        Orden de resolucion:
        1. Regla deterministica (RULES dict)
        2. Heuristica para casos ambiguos
        3. Fallback LLM (FLASH) si hay cliente disponible
        4. Default: final_report
        """
        # 1. Regla directa
        if current_step in RULES:
            return RULES[current_step]

        # 2. Casos ambiguos con heuristica
        if current_step == "reduce_synthesize":
            return self._resolve_after_reduce(state)

        if current_step == "theosampler_evaluate":
            return self._resolve_after_theosampler(state)

        # 3. Fallback LLM (solo si se proporciono cliente)
        if self.llm is not None:
            try:
                return self._llm_fallback(current_step, state)
            except Exception as e:
                logger.warning("Orchestrator LLM fallback failed: %s", e)

        # 4. Default seguro
        logger.warning(
            "Orchestrator: no rule for step=%s. Defaulting to final_report.",
            current_step,
        )
        return "final_report"

    # ── Heuristicas para casos ambiguos ───────────────────────────

    def _resolve_after_reduce(self, state: dict[str, Any]) -> str:
        """Despues de reduce_synthesize: ¿buscar core concern o seguir generando?

        Heuristica:
        - Si ya tenemos main_concern → generar hipotesis
        - Si tenemos >= 3 codigos → buscar core concern
        - Si tenemos < 3 codigos → seguir generando (batch_code)
        """
        if state.get("main_concern"):
            logger.info("Orchestrator: main_concern found → generate_hypotheses")
            return "generate_hypotheses"

        codes_count = len(state.get("new_codes", []))
        if codes_count >= 3:
            logger.info("Orchestrator: %d codes → find_core_concern", codes_count)
            return "find_core_concern"

        logger.info("Orchestrator: only %d codes → batch_code (need more)", codes_count)
        return "batch_code"

    def _resolve_after_theosampler(self, state: dict[str, Any]) -> str:
        """Despues de evaluar gaps de muestreo: ¿revisar gaps o avanzar?

        Heuristica:
        - Si hay gaps criticos → pausar para revision humana
        - Si solo hay warnings → avanzar al playground
        - Si no hay gaps → playground directo
        """
        gaps = state.get("pending_gaps", [])
        if not gaps:
            logger.info("Orchestrator: no gaps → prepare_playground")
            return "prepare_playground"

        critical = [g for g in gaps if g.get("severity") == "critical"]
        if critical:
            logger.info(
                "Orchestrator: %d critical gaps → hitl_gap_review", len(critical)
            )
            return "hitl_gap_review"

        logger.info(
            "Orchestrator: %d warnings (no critical) → prepare_playground",
            len(gaps),
        )
        return "prepare_playground"

    # ── Fallback LLM ──────────────────────────────────────────────

    def _llm_fallback(self, current_step: str, state: dict[str, Any]) -> str:
        """Ultimo recurso: preguntar al LLM (FLASH, ~50 tokens)."""
        if self.llm is None:
            return "final_report"

        prompt = f"""[ESTADO DEL PIPELINE]
Step actual: {current_step}
Project ID: {state.get("project_id", "")}
Documentos procesados: {state.get("docs_processed", 0)}
Codigos generados: {len(state.get("new_codes", []))}
Hipotesis candidatas: {len(state.get("candidate_hypotheses", []))}
Main concern: {"si" if state.get("main_concern") else "no"}
Gaps pendientes: {len(state.get("pending_gaps", []))}
Errores: {len(state.get("errors", []))}

[NODOS DISPONIBLES]
{", ".join(VALID_NODES)}

Responde SOLO el nombre del proximo nodo, sin explicacion.
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=20,
        )
        content = response.get("content", "").strip().lower()

        for node in VALID_NODES:
            if node in content:
                logger.info("Orchestrator LLM fallback: %s → %s", current_step, node)
                return node

        return "final_report"
