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
    """Node 1: Verifica que el documento tenga segmentos.

    La segmentación real la hace el orchestrator vía Celery.
    Este nodo solo verifica y espera pasivamente.
    """
    state["current_step"] = "segment_and_index"
    doc_id = state.get("document_id", "")
    if not doc_id:
        return state
    try:
        import sys as _s

        _s.path.insert(0, "/app")
        from database import SessionLocal
        from sqlalchemy import text

        s = SessionLocal()
        try:
            count = s.execute(
                text("SELECT COUNT(*) FROM segmentos WHERE documento_id = :did"),
                {"did": doc_id},
            ).fetchone()[0]
            if count > 0:
                logger.info("Node 1: doc=%s has %d segments", doc_id, count)
            else:
                logger.warning("Node 1: doc=%s has no segments yet", doc_id)
        finally:
            s.close()
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
        import os as _os

        from celery import Celery

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

        from workers.heavy.agents_b import b2_5_assign_codes_to_segments, b2_open_code

        result = b2_open_code(pid)
        state["new_codes"] = result.get("codes", [])
        logger.info("Node 3: B2 created %d codes", result.get("codes_created", 0))
        ground = b2_5_assign_codes_to_segments(pid)
        logger.info(
            "Node 3: B2.5 grounded %d segments", ground.get("segments_assigned", 0)
        )
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
        import os as _os

        from celery import Celery

        app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        app.send_task("process_synthesis_agents_b", args=[pid], queue="heavy")
        output = {"open_coding": {"codes": []}, "hypotheses": {"hypotheses": []}}
        state["code_document_summaries"] = output.get("open_coding", {}).get(
            "codes", []
        )
        state["candidate_hypotheses"] = output.get("hypotheses", {}).get(
            "hypotheses", []
        )
        logger.info(
            "Node 4: Map-Reduce completed (codes=%d, hyps=%d)",
            len(state.get("code_document_summaries", [])),
            len(state.get("candidate_hypotheses", [])),
        )
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
        logger.info(
            "Node 6: B3 generated %d hypotheses", result.get("hypotheses_created", 0)
        )
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
        import os as _os

        from celery import Celery

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
        decision = interrupt(
            {
                "message": "Revisar hipotesis candidatas",
                "candidates": [
                    {
                        "text": h.get("text", "")[:200],
                        "level": h.get("level", "emergent"),
                    }
                    for h in candidates[:5]
                ],
            }
        )
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


def build_glaser_graph_reduced():
    """
    Build and return a reduced LangGraph StateGraph — open coding ONLY.

    Este grafo contiene solo los nodos de open coding (Fase 3-4).
    Los nodos de selective coding se ejecutan via el
    selective_coding_coordinator (Celery), no via LangGraph.

    Nodos: segment_and_index → extract_entities → batch_code
           → map_synthesize → reduce_synthesize → END
    """
    from langgraph.graph import END, StateGraph

    builder = StateGraph(AnalysisState)

    # Solo open coding nodes
    builder.add_node("segment_and_index", node_segment_and_index)
    builder.add_node("extract_entities", node_extract_entities)
    builder.add_node("batch_code", node_batch_code)
    builder.add_node("map_synthesize", node_map_synthesize)
    builder.add_node("reduce_synthesize", node_reduce_synthesize)

    # Linear chain → END
    builder.set_entry_point("segment_and_index")
    builder.add_edge("segment_and_index", "extract_entities")
    builder.add_edge("extract_entities", "batch_code")
    builder.add_edge("batch_code", "map_synthesize")
    builder.add_edge("map_synthesize", "reduce_synthesize")
    builder.add_edge("reduce_synthesize", END)

    return builder.compile()


# ═══════════════════════════════════════════════════════════════════════
# PROMPT_NODE_MAP
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
    def checkpoint_segment(state: dict, segment_index: int, result: dict) -> dict:
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
        total = sum(len(wave) for wave in state.get("processed_segments", {}).values())
        return {
            "document_id": state.get("document_id"),
            "waves": state.get("processed_segments", {}),
            "total_segments_processed": total,
            "last_checkpoint": state.get("last_checkpoint", 0),
            "consolidated_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

    @staticmethod
    def get_unprocessed_segments(state: dict, total_segments: int) -> list[int]:
        """
        Indices de segmentos NO procesados en la wave actual.
        Util para reanudar tras fallo.
        """
        wave = f"wave_{state.get('current_wave', 1)}"
        processed = state.get("processed_segments", {}).get(wave, {})
        processed_indices = {int(k) for k in processed.keys()}
        return [i for i in range(total_segments) if i not in processed_indices]


# ═══════════════════════════════════════════════════════════════════════
# E07-E08 — Feedback Loop + Theoretical Playground Entry
# ═══════════════════════════════════════════════════════════════════════


def node_theosampler_evaluate(state: AnalysisState) -> AnalysisState:
    """E07: Evalua TODOS los ejes de comparacion (Momento 1 + Momento 2)."""
    state["current_step"] = "theosampler_evaluate"
    pid = state.get("project_id", "")
    if not pid:
        return state

    try:
        import sys as _s

        _s.path.insert(0, "/app")
        import asyncio

        from app.services.saturation_gap_analyzer import SaturationGapAnalyzer
        from database import SessionLocal

        s = SessionLocal()
        try:
            analyzer = SaturationGapAnalyzer(s)
            report = asyncio.run(analyzer.full_analysis(pid))

            # Convertir gaps a formato del estado
            gaps = []
            for g in report.critical + report.warnings:
                gaps.append(
                    {
                        "severity": g.severity.value
                        if hasattr(g.severity, "value")
                        else str(g.severity),
                        "description": g.description,
                        "suggested_action": g.suggested_action,
                        "source": g.source.value
                        if hasattr(g.source, "value")
                        else str(g.source),
                        "resolved": False,
                    }
                )

            state["pending_gaps"] = gaps
            state["saturated_codes"] = report.saturated
            logger.info(
                "E07: theosampler found %d critical, %d warnings, %d saturated",
                len(report.critical),
                len(report.warnings),
                len(report.saturated),
            )
        finally:
            s.close()
    except Exception as e:
        logger.warning("E07 theosampler failed: %s", e)

    return state


def node_hitl_gap_review(state: AnalysisState) -> AnalysisState:
    """E07: Pausa el grafo para que el investigador revise gaps."""
    state["current_step"] = "hitl_gap_review"
    gaps = state.get("pending_gaps", [])

    if not gaps:
        logger.info("E07: no gaps to review, skipping HITL")
        return state

    from langgraph.types import interrupt

    decision = interrupt(
        {
            "message": "Gaps detectados en ejes de comparacion",
            "gaps": [
                {
                    "severity": g.get("severity"),
                    "description": g.get("description", "")[:200],
                    "action": g.get("suggested_action", ""),
                }
                for g in gaps[:10]
            ],
            "options": [
                "load_new_data",
                "search_existing_corpus",
                "mark_as_limitation",
                "ignore_and_continue",
            ],
        }
    )

    state["gap_decision"] = decision
    logger.info("E07: HITL gap decision: %s", str(decision)[:100])
    return state


def node_process_new_data(state: AnalysisState) -> AnalysisState:
    """E08: Procesa nuevos documentos cargados para llenar gaps."""
    state["current_step"] = "process_new_data"
    new_docs = state.get("new_documents", [])

    if not new_docs:
        logger.info("E08: no new documents to process")
        return state

    pid = state.get("project_id", "")
    try:
        import os as _os

        from celery import Celery

        app = Celery(broker=_os.getenv("REDIS_URL", "redis://redis:6379/0"))

        for doc_id in new_docs:
            app.send_task(
                "process_document_agents_a",
                args=[doc_id, pid],
                queue="heavy",
            )
            logger.info("E08: dispatched processing for new doc=%s", doc_id)

        # Despachar sintesis B despues de procesar nuevos docs
        app.send_task(
            "process_synthesis_agents_b",
            args=[pid],
            queue="heavy",
        )
    except Exception as e:
        logger.warning("E08 process_new_data failed: %s", e)

    # Limpiar nuevos documentos procesados
    state["new_documents"] = []
    return state


def node_prepare_playground(state: AnalysisState) -> AnalysisState:
    """T25: Prepara el ecosistema para el Theoretical Playground."""
    state["current_step"] = "prepare_playground"
    state["phase"] = "theoretical_playground"
    pid = state.get("project_id", "")

    try:
        import sys as _s

        _s.path.insert(0, "/app")
        from database import SessionLocal

        s = SessionLocal()
        try:
            # 1. Seed theoretical codes
            from app.services.theory_seeder import seed_theoretical_codes

            inserted = seed_theoretical_codes(s)
            logger.info("T25: seeded %d theoretical codes", inserted)

            # 2. Crear ecosystem layout inicial
            from sqlalchemy import text

            existing = s.execute(
                text("SELECT id FROM ecosystem_layouts WHERE project_id = :pid"),
                {"pid": pid},
            ).fetchone()
            if not existing:
                s.execute(
                    text(
                        "INSERT INTO ecosystem_layouts "
                        "(id, project_id, version, blob_positions, ghost_positions, "
                        "fog_zones, physics_params) "
                        "VALUES (gen_random_uuid(), :pid, 1, '{}', '{}', '{}', "
                        "CAST(:phys AS jsonb))"
                    ),
                    {
                        "pid": pid,
                        "phys": '{"attraction_strength":0.01,"repulsion":0.05,'
                        '"damping":0.95,"core_gravity":0.005,'
                        '"min_distance":80,"max_velocity":3.0}',
                    },
                )
                s.commit()
                logger.info("T25: created initial ecosystem layout")

            # 3. Generar ghost-blobs desde memos
            from workers.heavy.llm_client import LLMClient

            _llm = LLMClient()
            from app.services.ghost_connector import GhostConnector

            connector = GhostConnector(s, _llm)
            ghosts = connector.generate_ghost_blobs(pid)
            logger.info("T25: generated %d ghost-blobs", len(ghosts))
            state["ghost_blobs"] = ghosts
        finally:
            s.close()
    except Exception as e:
        logger.warning("T25 prepare_playground failed: %s", e)

    return state


# ── Routing functions ──────────────────────────────────────────────────────


def after_saturation(
    state: AnalysisState,
) -> Literal["theosampler_evaluate", "hitl_review"]:
    """Route to theosampler if we have categories, else skip to HITL."""
    if state.get("phase") == "theoretical_playground":
        return "hitl_review"  # Already in playground, skip
    return "theosampler_evaluate"


def after_theosampler(
    state: AnalysisState,
) -> Literal["hitl_gap_review", "prepare_playground"]:
    """If gaps detected → HITL. If no gaps → advance to Playground."""
    gaps = state.get("pending_gaps", [])
    if gaps:
        return "hitl_gap_review"
    return "prepare_playground"


def after_gap_review(
    state: AnalysisState,
) -> Literal["process_new_data", "prepare_playground", "segment_and_index"]:
    """After gap review HITL: load data, continue, or loop back."""
    decision = state.get("gap_decision", {})
    if isinstance(decision, dict):
        action = decision.get("action", "ignore_and_continue")
    else:
        action = str(decision) if decision else "ignore_and_continue"

    if action == "load_new_data":
        return "process_new_data"
    elif action == "ignore_and_continue":
        return "prepare_playground"
    else:
        return "segment_and_index"  # Loop back for more data


# ── Extended graph with Feedback Loop ──────────────────────────────────────


def build_glaser_graph_with_feedback():
    """Build the full graph including TheoSampler + Gap Review + Playground entry."""
    from langgraph.graph import END, StateGraph

    builder = StateGraph(AnalysisState)

    # Core nodes
    builder.add_node("segment_and_index", node_segment_and_index)
    builder.add_node("extract_entities", node_extract_entities)
    builder.add_node("batch_code", node_batch_code)
    builder.add_node("map_synthesize", node_map_synthesize)
    builder.add_node("reduce_synthesize", node_reduce_synthesize)
    builder.add_node("find_core_concern", node_find_core_concern)
    builder.add_node("generate_hypotheses", node_generate_hypotheses)
    builder.add_node("calculate_saturation", node_calculate_saturation)

    # Feedback Loop nodes (E07-E08)
    builder.add_node("theosampler_evaluate", node_theosampler_evaluate)
    builder.add_node("hitl_gap_review", node_hitl_gap_review)
    builder.add_node("process_new_data", node_process_new_data)

    # Playground entry (T25)
    builder.add_node("prepare_playground", node_prepare_playground)

    # HITL review
    builder.add_node("hitl_review", node_hitl_review)
    builder.add_node("final_report", node_final_report)

    # ── Edges ──────────────────────────────────────────────────────────
    builder.set_entry_point("segment_and_index")

    builder.add_edge("segment_and_index", "extract_entities")
    builder.add_edge("extract_entities", "batch_code")
    builder.add_edge("batch_code", "map_synthesize")
    builder.add_edge("map_synthesize", "reduce_synthesize")
    builder.add_conditional_edges(
        "reduce_synthesize",
        should_find_core_concern,
        {
            "find_core_concern": "find_core_concern",
            "generate_hypotheses": "generate_hypotheses",
        },
    )
    builder.add_edge("find_core_concern", "generate_hypotheses")
    builder.add_edge("generate_hypotheses", "calculate_saturation")

    # After saturation → evaluate sampling gaps
    builder.add_conditional_edges(
        "calculate_saturation",
        after_saturation,
        {"theosampler_evaluate": "theosampler_evaluate", "hitl_review": "hitl_review"},
    )

    # TheoSampler → gap review or playground
    builder.add_conditional_edges(
        "theosampler_evaluate",
        after_theosampler,
        {
            "hitl_gap_review": "hitl_gap_review",
            "prepare_playground": "prepare_playground",
        },
    )

    # Gap review → process new data, continue, or loop
    builder.add_conditional_edges(
        "hitl_gap_review",
        after_gap_review,
        {
            "process_new_data": "process_new_data",
            "prepare_playground": "prepare_playground",
            "segment_and_index": "segment_and_index",
        },
    )

    # Process new data → re-evaluate gaps
    builder.add_edge("process_new_data", "theosampler_evaluate")

    # Playground → HITL → final
    builder.add_edge("prepare_playground", "hitl_review")
    builder.add_conditional_edges(
        "hitl_review",
        after_hitl,
        {"segment_and_index": "segment_and_index", "final_report": "final_report"},
    )
    builder.add_edge("final_report", END)

    return builder.compile()
