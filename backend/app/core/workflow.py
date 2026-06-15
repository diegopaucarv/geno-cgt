"""
LangGraph StateGraph — Glaser CGT Pipeline.

Reproduces the full sequence diagram:
  Document → Segment → Extract Entities → Batch Code (Producer+Critic)
  → Map Synthesis → Reduce Synthesis → Core Concern → Hypotheses
  → Saturation → HITL → (loop or Final Report)

Each node references a PromptTemplate from app.prompts by prompt_id.
Nodes that don't call an LLM (segmenter, indexer, saturation calc) are
pure Python functions.

Architecture:
  - StateGraph[AnalysisState] with typed state
  - checkpointed via PostgresSaver (langgraph-checkpoint-postgres)
  - invoked via Celery task run_phase_intent() on heavy_tasks queue
  - HITL via LangGraph interrupt() for hypothesis review
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Optional, TypedDict

from app.core.llm_config import PROMPT_TIER_MAP, get_model_for_prompt

logger = logging.getLogger(__name__)

# ── State definition ───────────────────────────────────────────────────────
# This TypedDict defines every field the StateGraph reads/writes.
# It mirrors the input_state / output_state metadata in each prompt .md file.


class AnalysisState(TypedDict, total=False):
    # ── Document-level ──────────────────────────────────────────────────
    project_id: str
    document_id: str
    document_text: str
    document_summary: str  # output of summarize_document (flash)
    topic_labels: list[str]  # output of summarize_document (flash)

    # ── Segment-level ───────────────────────────────────────────────────
    unprocessed_segments: list[dict]  # [{segment_id, text, position}]
    coded_segments: list[dict]  # [{segment_id, code_id, code_label, ...}]

    # ── Entity/Graph ────────────────────────────────────────────────────
    graph_entities: list[dict]  # output of extract_entities (flash)
    graph_relations: list[dict]  # output of extract_entities (flash)

    # ── Code-level ──────────────────────────────────────────────────────
    existing_codes: list[dict]  # [{code_id, label, definition, centroid_embedding}]
    code_prototypes: dict[str, list[str]]  # code_id → [segment_id, ...]
    proposed_codes: list[dict]  # output of batch_coder_producer
    code_evaluations: list[dict]  # output of batch_coder_critic
    new_codes: list[dict]  # codes accepted (SAT or MOD)
    modified_codes: list[dict]  # codes MOD with suggestions
    codes_to_reject: list[str]  # code_ids marked FORCED

    # ── Synthesis ───────────────────────────────────────────────────────
    code_document_summaries: list[dict]  # output of map_synthesis
    code_global_summaries: list[dict]  # output of reduce_synthesis
    cooccurrence_matrix: dict[str, dict]  # code_id → {code_id: count}

    # ── Core Concern ────────────────────────────────────────────────────
    main_concern: str  # output of core_concern_finder
    core_category_candidates: list[dict]  # output of core_concern_finder

    # ── Hypotheses ──────────────────────────────────────────────────────
    candidate_hypotheses: list[dict]  # output of hypothesis_generation
    confirmed_hypotheses: list[dict]  # after HITL accept
    rejected_hypotheses: list[dict]  # after HITL reject

    # ── Saturation ──────────────────────────────────────────────────────
    saturation_metrics: dict[
        str, dict
    ]  # code_id → {centroid, rolling_std, status, docs_since_change}
    extracted_incidents: list[dict]  # output of incident_extractor (flash)

    # ── Final ───────────────────────────────────────────────────────────
    final_report: dict  # output of final_report

    # ── Flow control ────────────────────────────────────────────────────
    study_status: str  # 'collecting' | 'closed'
    current_step: str  # for checkpointing / resume
    errors: list[str]  # accumulated errors

    # ── A8: Mem CP + Mem LP state ─────────────────────────────────────────
    processed_segments: dict[str, dict]  # wave_key → {segment_index: result}
    current_wave: int  # wave number for multi-pass coding
    last_checkpoint: int  # last segment index checkpointed


# ── Node implementations ───────────────────────────────────────────────────
# Each node is a function (AnalysisState) → AnalysisState.
# LLM calls use TogetherLLM.invoke_prompt(template, **state_fields).
# Pure-code nodes don't call LLMs.


def node_segment_and_index(state: AnalysisState) -> AnalysisState:
    """Node 1: Segmenta y genera embeddings (spaCy + TEI)."""
    state["current_step"] = "segment_and_index"
    doc_id = state.get("document_id", "")
    if not doc_id:
        return state
    try:
        import sys as _s
        _s.path.insert(0, "/app")
        from database import SessionLocal
        s = SessionLocal()
        try:
            from workers.heavy.tasks import _ensure_segmented
            _ensure_segmented(s, doc_id)
        finally:
            s.close()
        logger.info("Node 1: segmented doc=%s", doc_id)
    except Exception as e:
        logger.warning("Node 1 failed: %s", e)
    return state


def node_extract_entities(state: AnalysisState) -> AnalysisState:
    """Node 2: GraphRAG extraction — dispatch to worker-fast (fire-and-forget)."""
    state["current_step"] = "extract_entities"
    doc_id = state.get("document_id", "")
    pid = state.get("project_id", "")
    if not doc_id:
        return state
    try:
        from celery import Celery
        import os as _os
        app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        app.send_task("batch_extract_graph", args=[doc_id, pid], queue="fast")
        logger.info("Node 2: GraphRAG dispatched for doc=%s", doc_id)
    except Exception as e:
        logger.warning("Node 2 failed (non-blocking): %s", e)
    return state


def node_batch_code(state: AnalysisState) -> AnalysisState:
    """Node 3: Open coding (B2) + Grounding (B2.5)."""
    state["current_step"] = "batch_code"
    pid = state.get("project_id", "")
    if not pid:
        return state
    try:
    import sys as _sys
    _sys.path.insert(0, "/app")
    from database import SessionLocal
    from llm_client import LLMClient
    _llm = LLMClient()

        from workers.heavy.agents_b import b2_open_code, b2_5_assign_codes_to_segments
        result = b2_open_code(pid)
        state["new_codes"] = result.get("codes", [])
        logger.info("Node 3: B2 created %d codes", result.get("codes_created", 0))
        ground = b2_5_assign_codes_to_segments(pid)
        logger.info("Node 3: B2.5 grounded %d segments", ground.get("segments_assigned", 0))
    except Exception as e:
        logger.warning("Node 3 failed: %s", e)
    return state


def node_map_synthesize(state: AnalysisState) -> AnalysisState:
    """Node 4: Map-Reduce completo via Celery (reusa process_synthesis_agents_b)."""
    state["current_step"] = "map_synthesize"
    pid = state.get("project_id", "")
    if not pid:
        return state
    try:
        from celery import Celery
        import os as _os
        app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        result = app.send_task("process_synthesis_agents_b", args=[pid], queue="heavy")
        output = result.get(timeout=600)
        state["code_document_summaries"] = output.get("open_coding", {}).get("codes", [])
        state["candidate_hypotheses"] = output.get("hypotheses", {}).get("hypotheses", [])
        logger.info("Node 4: Map-Reduce completed (codes=%d, hyps=%d)",
            len(state.get("code_document_summaries", [])),
            len(state.get("candidate_hypotheses", [])))
    except Exception as e:
        logger.warning("Node 4 Map-Reduce failed (non-blocking): %s", e)
    return state


def node_reduce_synthesize(state: AnalysisState) -> AnalysisState:
    """Node 5: Reduce phase — handled by node_map_synthesize (Celery task)."""
    state["current_step"] = "reduce_synthesize"
    logger.info("Node 5: reduce_synthesize — delegated to B agents")
    return state


def node_find_core_concern(state: AnalysisState) -> AnalysisState:
    """Node 5.5: A14 Main Concern usando 3 preguntas operacionales."""
    if state.get("main_concern"):
        return state
    state["current_step"] = "find_core_concern"
    try:
        import sys as _s
        _s.path.insert(0, "/app")
        from workers.heavy.tasks import task_a14_main_concern
        result = task_a14_main_concern(state["project_id"])
        state["main_concern"] = result.get("main_concern", "")
        logger.info("Node 5.5: main_concern=%s", state["main_concern"][:60])
    except Exception as e:
        logger.warning("Node 5.5 failed: %s", e)
    return state


def node_generate_hypotheses(state: AnalysisState) -> AnalysisState:
    """Node 6: B3 Hypothesis generation (reuses existing if Map-Reduce already did it)."""
    state["current_step"] = "generate_hypotheses"
    pid = state.get("project_id", "")
    if state.get("candidate_hypotheses"):
        logger.info("Node 6: hypotheses already generated by Map-Reduce")
        return state
    if not pid:
        return state
    try:
    import sys as _sys
    _sys.path.insert(0, "/app")
    from database import SessionLocal
    from llm_client import LLMClient
    _llm = LLMClient()

        from workers.heavy.agents_b import b3_generate_hypotheses
        result = b3_generate_hypotheses(pid)
        state["candidate_hypotheses"] = result.get("hypotheses", [])
        logger.info("Node 6: B3 generated %d hypotheses", result.get("hypotheses_created", 0))
    except Exception as e:
        logger.warning("Node 6 failed: %s", e)
    return state


def node_calculate_saturation(state: AnalysisState) -> AnalysisState:
    """Node 7: SaturationCalculator + Paradigm SQL check."""
    state["current_step"] = "calculate_saturation"
    pid = state.get("project_id", "")
    if not pid:
        return state
    try:
        from celery import Celery
        import os as _os
        app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        app.send_task("update_saturation", args=[pid], queue="nlp")
        logger.info("Node 7: saturation dispatched for project %s", pid)
    except Exception as e:
        logger.warning("Node 7 failed (non-blocking): %s", e)
    return state


def node_hitl_review(state: AnalysisState) -> AnalysisState:
    """Node 8: HITL — pausa el grafo para revision humana de hipotesis."""
    state["current_step"] = "hitl_review"
    from langgraph.types import interrupt
    candidates = state.get("candidate_hypotheses", [])
    if candidates:
        decision = interrupt({
            "message": "Revisar hipotesis candidatas",
            "candidates": [
                {"text": h.get("text", "")[:200], "level": h.get("level", "emergent")}
                for h in candidates[:5]
            ],
        })
        state["hitl_decision"] = decision
        logger.info("Node 8: HITL decision received")
    else:
        logger.info("Node 8: HITL skipped (no candidates)")
    return state


def node_final_report(state: AnalysisState) -> AnalysisState:
    """Node 9: Final report — placeholder (Fase 14 del Plan.md)."""
    state["current_step"] = "final_report"
    state["final_report"] = {
        "status": "placeholder",
        "message": "Final report generation not yet implemented (Fase 14)",
        "main_concern": state.get("main_concern", ""),
        "hypotheses_count": len(state.get("candidate_hypotheses", [])),
    }
    logger.info("Node 9: final_report placeholder")
    return state


# ── Conditional routing ─────────────────────────────────────────────────────
# These functions decide which edge to take based on state.


def should_find_core_concern(
    state: AnalysisState,
) -> Literal["find_core_concern", "generate_hypotheses"]:
    """Skip core_concern_finder if main_concern already set."""
    if state.get("main_concern"):
        return "generate_hypotheses"
    return "find_core_concern"


def should_continue_collecting(
    state: AnalysisState,
) -> Literal["segment_and_index", "final_report"]:
    """Route based on study_status."""
    if state.get("study_status") == "closed":
        return "final_report"
    return "segment_and_index"


def after_hitl(state: AnalysisState) -> Literal["segment_and_index", "final_report"]:
    """After HITL review, either loop for more data or close."""
    if state.get("study_status") == "closed":
        return "final_report"
    return "segment_and_index"


# ── Build the StateGraph ────────────────────────────────────────────────────
# Called from Celery task: run_phase_intent(project_id, document_ids)


def build_glaser_graph():
    """
    Build and return the compiled LangGraph StateGraph.

    Usage:
        from langgraph.checkpoint.postgres import PostgresSaver

        graph = build_glaser_graph()
        saver = PostgresSaver.from_conn_string(DATABASE_URL)
        saver.setup()

        config = {"configurable": {"thread_id": project_id}}
        initial_state = AnalysisState(
            project_id=project_id,
            document_id=doc_id,
            document_text=text,
            study_status="collecting",
        )
        result = graph.invoke(initial_state, config)
    """
    from langgraph.graph import END, StateGraph

    builder = StateGraph(AnalysisState)

    # ── Add nodes ───────────────────────────────────────────────────────
    # Order matches execution_order metadata in prompt .md files.
    builder.add_node("segment_and_index", node_segment_and_index)  # 1
    builder.add_node("extract_entities", node_extract_entities)  # 2 (Flash)
    builder.add_node("batch_code", node_batch_code)  # 3 (Pro × 2)
    builder.add_node("map_synthesize", node_map_synthesize)  # 4 (Pro, parallel)
    builder.add_node("reduce_synthesize", node_reduce_synthesize)  # 5 (Pro)
    builder.add_node(
        "find_core_concern", node_find_core_concern
    )  # 5.5 (Pro, conditional)
    builder.add_node("generate_hypotheses", node_generate_hypotheses)  # 6 (Pro)
    builder.add_node("calculate_saturation", node_calculate_saturation)  # 6.1 (no LLM)
    builder.add_node("hitl_review", node_hitl_review)  # 6.2 (LangGraph interrupt)
    builder.add_node("final_report", node_final_report)  # 7 (Pro, on close)

    # ── Add edges ───────────────────────────────────────────────────────
    builder.set_entry_point("segment_and_index")

    # Linear chain:
    builder.add_edge("segment_and_index", "extract_entities")
    builder.add_edge("extract_entities", "batch_code")
    builder.add_edge("batch_code", "map_synthesize")
    builder.add_edge("map_synthesize", "reduce_synthesize")

    # Conditional: skip core_concern_finder if already set
    builder.add_conditional_edges(
        "reduce_synthesize",
        should_find_core_concern,
        {
            "find_core_concern": "find_core_concern",
            "generate_hypotheses": "generate_hypotheses",
        },
    )
    builder.add_edge("find_core_concern", "generate_hypotheses")

    # After hypotheses → saturation → HITL
    builder.add_edge("generate_hypotheses", "calculate_saturation")
    builder.add_edge("calculate_saturation", "hitl_review")

    # After HITL: either loop back or finish
    builder.add_conditional_edges(
        "hitl_review",
        after_hitl,
        {
            "segment_and_index": "segment_and_index",
            "final_report": "final_report",
        },
    )
    builder.add_edge("final_report", END)

    return builder.compile()


# ── Prompt-to-node mapping (for documentation and introspection) ────────────
# Generated from the langgraph_node metadata in each prompt .md file.

PROMPT_NODE_MAP: dict[str, str] = {
    # Flash prompts
    "entity_extraction": "extract_entities",  # Node 2
    "incident_extractor": "calculate_saturation",  # Node 6.1 (optional sub-step)
    "document_summarizer": "segment_and_index",  # Node 1.1 (optional pre-processing)
    "context_synthesizer": None,  # Legacy, not in main graph
    # Pro prompts
    "batch_coder_producer": "batch_code",  # Node 3.0
    "batch_coder_critic": "batch_code",  # Node 3.1
    "map_synthesis": "map_synthesize",  # Node 4
    "reduce_synthesis": "reduce_synthesize",  # Node 5
    "core_concern_finder": "find_core_concern",  # Node 5.5
    "hypothesis_generation": "generate_hypotheses",  # Node 6
    "clusterizador_informado": None,  # Manual fallback, not in main graph
    "final_report": "final_report",  # Node 7
}


# ═══════════════════════════════════════════════════════════════════════
# A8 — RollingWindowStateManager (Mem CP + Mem LP)
# ═══════════════════════════════════════════════════════════════════════

class RollingWindowStateManager:
    """
    Mem CP + Mem LP adaptado al estado de LangGraph.
    Equivalente al ciclo Mem CP -> Mem LP -> Read/Write Files de n8n.

    Mem CP: guarda el resultado de codificar UN segmento.
    Mem LP: consolida todos los segmentos al final del documento.

    Usa el estado del grafo (AnalysisState) en lugar de archivos /tmp.
    El checkpointing de LangGraph (PostgresSaver) persiste automáticamente.
    """

    @staticmethod
    def checkpoint_segment(
        state: dict, segment_index: int, result: dict
    ) -> dict:
        """
        Mem CP: guarda resultado de codificacion de UN segmento.
        Permite reanudar desde el ultimo segmento si el worker falla.
        Equivalente a alwaysOutputData: true — si la wave no existe, se crea.
        """
        wave = f"wave_{state.get('current_wave', 1)}"

        if "processed_segments" not in state:
            state["processed_segments"] = {}
        if wave not in state["processed_segments"]:
            state["processed_segments"][wave] = {}

        state["processed_segments"][wave][str(segment_index)] = {
            "text": result.get("text", ""),
            "study_question": result.get("study_question", ""),
            "data_type": result.get("glaser_data_type", ""),
            "main_concern": result.get("main_concern", ""),
            "code_label": result.get("code_label", ""),
            "checkpointed_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        state["last_checkpoint"] = segment_index
        return state

    @staticmethod
    def consolidate_loop(state: dict) -> dict:
        """
        Mem LP: consolida todos los segmentos al final del documento.
        Produce un resumen para la siguiente iteracion.
        """
        total = sum(
            len(wave)
            for wave in state.get("processed_segments", {}).values()
        )
        return {
            "document_id": state.get("document_id"),
            "waves": state.get("processed_segments", {}),
            "total_segments_processed": total,
            "last_checkpoint": state.get("last_checkpoint", 0),
            "consolidated_at": __import__("datetime")
            .datetime.utcnow()
            .isoformat(),
        }

    @staticmethod
    def get_unprocessed_segments(
        state: dict, total_segments: int
    ) -> list[int]:
        """
        Indices de segmentos NO procesados en la wave actual.
        Util para reanudar tras fallo.
        """
        wave = f"wave_{state.get('current_wave', 1)}"
        processed = state.get("processed_segments", {}).get(wave, {})
        processed_indices = {int(k) for k in processed.keys()}
        return [
            i for i in range(total_segments) if i not in processed_indices
        ]
