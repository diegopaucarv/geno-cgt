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


# ── Node implementations ───────────────────────────────────────────────────
# Each node is a function (AnalysisState) → AnalysisState.
# LLM calls use TogetherLLM.invoke_prompt(template, **state_fields).
# Pure-code nodes don't call LLMs.


def node_segment_and_index(state: AnalysisState) -> AnalysisState:
    """
    Node 1: Segment document using ProgressiveSegmenter (no LLM).
    Stores segments + embeddings in DB. Populates unprocessed_segments.
    """
    # ── Pure Python: calls ProgressiveSegmenter via Celery task ─────────
    # segmentar_y_indexar_documento(document_id) in worker-nlp
    # This node is a pass-through; the actual work happens in the worker.
    state["current_step"] = "segment_and_index"
    logger.info("Node 1: segment_and_index — dispatching to worker-nlp")
    return state


def node_extract_entities(state: AnalysisState) -> AnalysisState:
    """
    Node 2: Extract entities and relations from each segment (Flash).
    Uses prompt: entity_extraction (flash/entity_extraction.md)
    Parallelizable per segment.
    """
    state["current_step"] = "extract_entities"
    # template = get_prompt("entity_extraction")
    # for segment in state["unprocessed_segments"]:
    #     result = client.invoke_prompt(template, segment_text=segment["text"], segment_id=segment["id"])
    #     state["graph_entities"].extend(result["entities"])
    #     state["graph_relations"].extend(result["relations"])
    logger.info("Node 2: extract_entities — Flash model, per-segment extraction")
    return state


def node_batch_code(state: AnalysisState) -> AnalysisState:
    """
    Node 3: Batch code segments (Producer + Critic, both Pro).
    Sub-step 3.0: Producer → batch_coder_producer (pro/batch_coder_producer.md)
    Sub-step 3.1: Critic   → batch_coder_critic   (pro/batch_coder_critic.md)

    The Producer reuses existing codes when similarity > threshold;
    generates new codes when needed. The Critic evaluates each as SAT/MOD/FORCED.
    """
    state["current_step"] = "batch_code"
    # ── Step 3.0: Producer ──────────────────────────────────────────────
    # template = get_prompt("batch_coder_producer")
    # result = client.invoke_prompt(template,
    #     existing_codes=format_codes(state["existing_codes"]),
    #     similar_codes=format_similar(state["unprocessed_segments"], state["code_prototypes"]),
    #     segments_batch=format_segments(state["unprocessed_segments"]),
    # )
    # state["proposed_codes"] = result["codes"]

    # ── Step 3.1: Critic ────────────────────────────────────────────────
    # template = get_prompt("batch_coder_critic")
    # result = client.invoke_prompt(template,
    #     codes_to_evaluate=format_proposed(state["proposed_codes"]),
    #     evidence_segments=format_evidence(state["unprocessed_segments"]),
    #     existing_codes=format_codes(state["existing_codes"]),
    # )
    # state["code_evaluations"] = result["evaluations"]
    # state["new_codes"] = [c for c in proposed if eval[c["code_label"]]["verdict"] != "FORCED"]
    # state["codes_to_reject"] = [c["code_label"] for c in proposed if eval[c["code_label"]]["verdict"] == "FORCED"]
    logger.info("Node 3: batch_code — Pro Producer → Pro Critic")
    return state


def node_map_synthesize(state: AnalysisState) -> AnalysisState:
    """
    Node 4: Map phase — intra-document synthesis per code (Pro).
    Runs per (code × document) pair in parallel.
    Uses prompt: map_synthesis (pro/map_synthesis.md)
    """
    state["current_step"] = "map_synthesize"
    # template = get_prompt("map_synthesis")
    # for code in state["new_codes"] + state["modified_codes"]:
    #     for doc_id in get_docs_with_code(code["id"]):
    #         result = client.invoke_prompt(template,
    #             code_label=code["label"],
    #             code_definition=code["definition"],
    #             code_id=code["id"],
    #             document_name=get_doc_name(doc_id),
    #             document_id=doc_id,
    #             assigned_segments=get_segments_for_code_in_doc(code["id"], doc_id),
    #         )
    #         state["code_document_summaries"].append(result)
    logger.info("Node 4: map_synthesize — Pro, parallel per code×document")
    return state


def node_reduce_synthesize(state: AnalysisState) -> AnalysisState:
    """
    Node 5: Reduce phase — inter-document consolidation per code (Pro).
    Runs once per code after all Map tasks complete.
    Uses prompt: reduce_synthesis (pro/reduce_synthesis.md)
    """
    state["current_step"] = "reduce_synthesize"
    # template = get_prompt("reduce_synthesis")
    # for code in state["new_codes"] + state["modified_codes"]:
    #     summaries = [s for s in state["code_document_summaries"] if s["code_id"] == code["id"]]
    #     result = client.invoke_prompt(template,
    #         code_label=code["label"],
    #         code_definition=code["definition"],
    #         code_id=code["id"],
    #         intra_document_summaries=format_summaries(summaries),
    #         doc_count=len(summaries),
    #         segment_count=count_segments_for_code(code["id"]),
    #     )
    #     state["code_global_summaries"].append(result)
    logger.info("Node 5: reduce_synthesize — Pro, one per modified code")
    return state


def node_find_core_concern(state: AnalysisState) -> AnalysisState:
    """
    Node 5.5: Find main concern (Pro). Runs once per study if not set.
    Prerequisite for hypothesis_generation.
    Uses prompt: core_concern_finder (pro/core_concern_finder.md)
    """
    if state.get("main_concern"):
        logger.info("Node 5.5: core_concern_finder — SKIPPED (already set)")
        return state

    state["current_step"] = "find_core_concern"
    # template = get_prompt("core_concern_finder")
    # result = client.invoke_prompt(template,
    #     all_codes=format_all_codes(state["existing_codes"]),
    #     all_memos=format_all_memos(state.get("memos", [])),
    # )
    # state["main_concern"] = result["main_concern"]
    # state["core_category_candidates"] = result["core_category_candidates"]
    logger.info("Node 5.5: core_concern_finder — Pro, once per study")
    return state


def node_generate_hypotheses(state: AnalysisState) -> AnalysisState:
    """
    Node 6: Generate candidate hypotheses using Tree of Thoughts (Pro).
    Requires main_concern to be set (from core_concern_finder or manual).
    Uses prompt: hypothesis_generation (pro/hypothesis_generation.md)
    Post-action: stores hypotheses in DB with status='candidate', notifies HITL.
    """
    state["current_step"] = "generate_hypotheses"
    # template = get_prompt("hypothesis_generation")
    # result = client.invoke_prompt(template,
    #     main_concern=state["main_concern"],
    #     codes_with_synthesis=format_synthesis(state["code_global_summaries"]),
    #     cooccurrence_matrix=format_cooccurrence(state["cooccurrence_matrix"]),
    # )
    # state["candidate_hypotheses"] = result["hypotheses"]
    # ── Store in DB with status='candidate', notify HITL via WebSocket ──
    logger.info("Node 6: hypothesis_generation — Pro, ToT/GoD")
    return state


def node_calculate_saturation(state: AnalysisState) -> AnalysisState:
    """
    Node 6.1: Calculate saturation metrics (no LLM).
    Pure Python: moving centroid, rolling std, per-code status.
    Optionally calls incident_extractor (Flash) for new incidents.
    """
    state["current_step"] = "calculate_saturation"
    # ── Pure Python: update_saturation(code_id, new_segments) in worker-nlp ──
    # ── Optionally: incident_extractor for detailed per-category analysis ──
    logger.info("Node 6.1: calculate_saturation — code (no LLM)")
    return state


def node_hitl_review(state: AnalysisState) -> AnalysisState:
    """
    Node 6.2: HITL — Human reviews hypotheses via UI.
    This is a LangGraph interrupt() point. The graph pauses here.
    Researcher calls POST /hypotheses/decision → resumes graph.
    """
    state["current_step"] = "hitl_review"
    # ── LangGraph interrupt() — graph pauses, waits for human input ──
    # This is not an LLM call. The state is checkpointed by PostgresSaver.
    logger.info("Node 6.2: hitl_review — LangGraph interrupt(), awaiting human")
    return state


def node_final_report(state: AnalysisState) -> AnalysisState:
    """
    Node 7: Generate final study report (Pro).
    Triggered only when researcher closes the study (POST /study/close).
    Uses prompt: final_report (pro/final_report.md)
    """
    state["current_step"] = "final_report"
    # template = get_prompt("final_report")
    # result = client.invoke_prompt(template,
    #     main_concern=state["main_concern"],
    #     codes_with_global_summary=format_synthesis(state["code_global_summaries"]),
    #     confirmed_hypotheses=format_confirmed(state["confirmed_hypotheses"]),
    #     saturation_metrics=format_saturation(state["saturation_metrics"]),
    #     anomaly_register=format_anomalies(state.get("anomalies", [])),
    # )
    # state["final_report"] = result["report"]
    logger.info("Node 7: final_report — Pro, on study close")
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
