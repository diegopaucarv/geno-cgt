# Agent Data Production Analysis — Backend Gap Analysis

> **Date**: 2026-06-21
> **System**: GT (Grounded Theory / CGT Methodology)
> **Scope**: Pipeline Orchestrator, Agents, Tools, Services, Workers, Prompts

---

## Table of Contents

1. [Section 1: Agent Catalog](#section-1-agent-catalog)
   - [1.1 Core Engine Agents](#11-core-engine-agents)
   - [1.2 Data Management Agents (Stage 1)](#12-data-management-agents-stage-1)
   - [1.3 Open Coding Agents (Stage 2)](#13-open-coding-agents-stage-2)
   - [1.4 Synthesis & Cross-Document Agents (Stage 2→3 Bridge)](#14-synthesis--cross-document-agents-stage-23-bridge)
   - [1.5 Selective Coding Agents (Stage 3)](#15-selective-coding-agents-stage-3)
   - [1.6 Theoretical Coding Agents (Stage 4)](#16-theoretical-coding-agents-stage-4)
   - [1.7 Writing & Final Agents (Stage 5)](#17-writing--final-agents-stage-5)
   - [1.8 HITL & Meta-Agents](#18-hitl--meta-agents)
   - [1.9 Utility & Auxiliary Agents](#19-utility--auxiliary-agents)
2. [Section 2: Pipeline Stage Data Flow](#section-2-pipeline-stage-data-flow)
3. [Section 3: Service-to-DB Write Map](#section-3-service-to-db-write-map)

---

## Section 1: Agent Catalog

### 1.1 Core Engine Agents

#### OrchestratorRuleEngine (`orchestrator.py`)
- **Agent ID**: `orchestrator_rule_engine` (internal, not exposed to frontend)
- **What it does**: Deterministic rule engine (no LLM by default) that decides the next pipeline step. Uses `RULES` dict for 90% of transitions, heuristics for 2 ambiguous cases (`reduce_synthesize` → maturity gate check; `theosampler_evaluate` → gap severity check). Falls back to LLM (FLASH) only as last resort.
- **Prompt template**: None (rules-based). Only uses `_llm_fallback()` with inline prompt for LLM fallback.
- **Input data**: `current_step` (string), `state` dict containing: `core_concern`, `new_codes`, `saturated_categories`, `documented_relationships`, `categories_linked_to_concern`, `pending_gaps`, `errors`, `candidate_hypotheses`, `docs_processed`, `project_id`
- **Output data**: Next step name (e.g., `"final_report"`, `"hitl_gap_review"`, `"batch_code"`)
- **DB Writes**: None (read-only decision engine)
- **DB Reads**: None directly (reads from in-memory state dict)
- **Tools**: None

#### BaseAgent (`base.py`)
- **Agent ID**: Abstract base class — instantiated as subclasses
- **What it does**: Template Method pattern providing common infrastructure for all agent loops. Handles iteration counting, timeout, token tracking, reasoning preservation, and optional `AgentLoopLog` persistence.
- **Prompt template**: Abstract `_build_system_prompt()` — implemented by subclasses
- **Input data**: `project_id`, `**kwargs` (arbitrary)
- **Output data**: `AgentResult(success, data, iterations, total_tokens, total_cost_est, had_reasoning, trace, error)`
- **DB Writes**: Optional `AgentLoopLog` (traceability — not a DB table, just in-memory dataclass)
- **DB Reads**: None directly
- **Tools**: None (subclasses add their own)

#### PlanExecutor (`plan_executor.py`)
- **Agent ID**: Instantiated per-task (e.g., `"plan_executor_coding"`)
- **What it does**: Plan-and-Execute pattern. LLM creates a full plan (goal + steps), then executes each step with tools or LLM actions, evaluates results, and replans if needed. Used for multi-step tasks requiring global vision (project-wide coding, selective elaboration, saturation analysis).
- **Prompt template**: Inline system prompt with tools schema, no separate .md file
- **Input data**: `goal`, `state_summary`, `role_description`
- **Output data**: `{plan: {goal, steps, success_criteria}, results: [...], evaluation: {...}}`
- **DB Writes**: None directly (delegates to tool calls)
- **DB Reads**: Via tool calls only
- **Tools**: Full `ToolRegistry` — all registered tools

#### ReactRunner (`react_runner.py`)
- **Agent ID**: Instantiated per-task (e.g., `"react_coding_agent"`, `"hitl_modification_executor"`)
- **What it does**: ReAct loop (Thought → Action → Observation → ... → FinalAnswer). Supports two modes: text parsing (Thought:/Action:/Action Input:) and native function calling. Preserves `reasoning_content` for DeepSeek V4 Pro.
- **Prompt template**: Inline system prompt with tools schema
- **Input data**: `role_description`
- **Output data**: Parsed `FinalAnswer` JSON
- **DB Writes**: None directly (delegates to tool calls)
- **DB Reads**: Via tool calls only
- **Tools**: Full `ToolRegistry`

#### SelfRefinementLoop (`self_refiner.py`)
- **Agent ID**: Instantiated per-task (e.g., `"b2b_self_refiner"`)
- **What it does**: Generate → Algorithmic Check → LLM Critic → Refine → Converge loop. Uses PRO for generation, algorithmic checks (regex + embedding) for ~60% of validation (O6 optimization), FLASH critic only for qualitative issues. Skips LLM critic entirely when algorithmic check passes.
- **Prompt template**: `generate_prompt_id` + `critic_prompt_id` (injected at construction)
- **Input data**: `generate_vars`, `critic_vars`, `coding_style`
- **Output data**: Final refined `output` dict (e.g., `{codes: [...]}`)
- **DB Writes**: None directly (output goes to caller)
- **DB Reads**: None directly
- **Tools**: None (uses `llm.run_agent()` only)

#### ToolRegistry (`tool_registry.py`)
- **Agent ID**: Infrastructure — not an agent
- **What it does**: Centralized tool registry. Decorator-based (`@tool`), auto-discovery (`register_from_module()`), schema generation for prompts, OpenAI function calling format support.
- **Registered tools**: 12 total
  - **DB tools**: `get_all_codes`, `get_code_details`, `get_existing_hypotheses`
  - **Compare tools**: `compare_embeddings`, `find_similar_codes` (TEI-based)
  - **Search tools**: `search_segments`, `search_similar_codes` (RAG-based)
  - **Context Window tools**: `expand_incident`, `search_precise_entities`, `get_document_window`, `estimate_batch_tokens`, `batch_map_reduce`

#### HITLModificationAgent (`hitl_modifier.py`)
- **Agent ID**: `hitl_modification_agent` (P5 — Memo Modification with Agentic Verification)
- **What it does**: Orchestrates 5 phases: (1) FLASH filter classifies user request as valid/invalid, (2) PRO planner rewrites request + creates verification plan + falsification hypothesis, (3) ReactRunner executes plan with tools, (4) PRO evaluator decides if modification is recommended, (5) apply confirmed modifications — wipes dependent tables, restarts pipeline from checkpoint.
- **Prompt template**: `hitl_modification_filter`, `hitl_modification_planner`, `hitl_modification_evaluator`, `hitl_evidence_collector`
- **Input data**: `agent_id`, `user_request`, `current_memo`, `proyecto_id`, `original_prompt`
- **Output data**: `ModificationResult(valid_request, recommended, recommendation_confidence, modified_memo, impact_summary, applied, wiped_tables, pipeline_restarted_from)`
- **DB Writes**: Writes to any table via `_update_output()` and `_wipe_table()` — key tables: `categorias`, `proyectos`, `hypotheses`, `codigos_segmento`, `code_document_summaries`, `code_global_summaries`, `conceptual_relationships`, `elaboration_memos`, `saturation_metrics`
- **DB Reads**: `agent_families` (CHANGE_IMPACT_MAP)
- **Tools**: `search_segments`, `get_code_details`, `compare_embeddings`, `find_similar_codes`, `search_evidence_for_modification`, all CWM tools

---

### 1.2 Data Management Agents (Stage 1)

These run in the `process_document_agents_a` Celery task on the `heavy` queue, one document at a time.

#### `a1` — Population Context Builder (`a1_build_population_context`)
- **Agent ID**: `a1` / `a1_build_population_context`
- **What it does**: Long-term memory. Analyzes a new document's segments and expands cumulative understanding about the population across 3 dimensions: surprising details, language patterns, data production context. Iteratively builds knowledge with versioning.
- **Prompt template**: `fa_population_context` (agents/fa_population_context/prompt.md)
- **Input data**: `population_assumption`, `existing_context` (from DB), `segments` (≤8000 chars from documento), `object_of_study`, `operational_question`
- **Output data**: `{surprising_details: str, language_patterns: str, data_production_context: str}`
- **DB Writes**: **`population_contexts`** — `id`, `proyecto_id`, `surprising_details`, `language_patterns`, `data_production_context`, `source_document_ids` (JSONB array), `version`
- **DB Reads**: `proyectos` (supuesto_poblacional, population_assumption, object_of_study), `population_contexts` (latest version for existing context), `segmentos`
- **Tools**: None (pure LLM call)

#### `a2` — Process Identifier (`a2_identify_process`)
- **Agent ID**: `a2` / `a2_identify_process`
- **What it does**: Short-term memory per document. Identifies the central process (gerund form) that the participant is continually trying to resolve. First doc uses `a2_first` schema, subsequent docs use `a2_compare` schema to compare with previous doc's process.
- **Prompt template**: `fa_process_identifier` — with `a2_first` and `a2_compare` sub-schemas (agents/a2_first/prompt.md, agents/a2_compare/prompt.md)
- **Input data**: `segments`, `previous_process` (for compare mode), `object_of_study`, `coding_style_instruction`
- **Output data**: `{process_description: str, similarity_to_previous?: str, difference_from_previous?: str}`
- **DB Writes**: **`document_processes`** — `id`, `documento_id`, `process_description`, `similarity_to_previous`, `difference_from_previous`, `proyecto_id`
- **DB Reads**: `segmentos`, `document_processes` (previous doc's process), `proyectos`
- **Tools**: None

#### `a3` — Sense Maker (`a3_make_sense`)
- **Agent ID**: `a3` / `a3_make_sense`
- **What it does**: Emergent hypothesis generation. Runs from document 3 onward. Evaluates whether each new document modifies, changes substantially, or doesn't change the emerging understanding, and generates hypotheses.
- **Prompt template**: `fa_sense_maker` (agents/fa_sense_maker/prompt.md)
- **Input data**: All processes from previous documents, all existing hypotheses memos, current document segments, `population_assumption`
- **Output data**: `{sense_status: "modifies"|"changes_substantially"|"no_change", hypotheses: [{text, level, evidence}]}`
- **DB Writes**: **`memos`** — inserts hypothesis memos (`tipo='HIPOTESIS'`). **`document_processes`** — updates `process_description`, `sense_status`. **`hypotheses`** — inserts new hypotheses (from doc 3+).
- **DB Reads**: `document_processes` (all previous), `memos`, `segmentos`, `proyectos`
- **Tools**: None

#### `extract_patterns_and_incidents` (F2.3 unified PRO call)
- **Agent ID**: N/A — internal function called from `process_document_agents_a` step 0.5
- **What it does**: Replaces 3 old tasks (per-segment `extract_incident` + `extract_core_pattern` + `_extract_prime_mover`) with ONE PRO call per document. Extracts behavioral patterns, incidents (coded segments), and document signals (prime mover).
- **Prompt template**: Called from `pattern_extractor` module (external to prompts/ agents directory)
- **Input data**: Document segments, project context
- **Output data**: `{patterns: [...], incidents_count: int, document_signals: {prime_mover, ...}}`
- **DB Writes**: **`incident_groups`** (via internal mechanism). **`document_processes`** — updates `prime_mover`, `prime_mover_confidence`
- **DB Reads**: `segmentos`
- **Tools**: None

#### `_classify_glaser_types_for_doc`
- **Agent ID**: N/A — internal function, uses LLM fallback
- **What it does**: F2.1 — pre-classify each segment's data type according to Glaser's typology (baseline, vague, etc.) to prepare for open coding.
- **Prompt template**: `fa_glaser_data_classifier` (agents/fa_glaser_data_classifier/prompt.md)
- **Input data**: Segments from document
- **Output data**: Glaser type classification per segment
- **DB Writes**: **`segmentos`** — updates `glaser_type` column
- **DB Reads**: `segmentos`
- **Tools**: None

#### `task_a06_theoretical_sample` (TheoSampler)
- **Agent ID**: `theosampler_evaluate` (node name in pipeline graph)
- **What it does**: Theoretical sampling recommendation. Analyzes under-sampled categories and suggests which participant demographics/documents to collect next.
- **Prompt template**: Used via `EmergentSampler` (see services) — prompts: `fe_corpus_scanner` (FLASH), `fe_property_sampler` (PRO)
- **Input data**: Categories from DB, paradigm states, segments
- **Output data**: `SamplingResult` with `property_name`, `target_extreme`, `found_incidents`, `sampling_recommendation`, `suggested_interview_question`
- **DB Writes**: **`sampling_memos`** (if applicable). No direct table writes identified.
- **DB Reads**: `categorias`, `paradigm_states`, `segmentos`, `codigos_segmento`
- **Tools**: None (LLM-only)

---

### 1.3 Open Coding Agents (Stage 2)

These run in `process_synthesis_agents_b` Celery task on the `heavy` queue.

#### `b1_group_incidents` — Incident Comparator/Grouper
- **Agent ID**: `b1` / `b1_group_incidents`
- **What it does**: F2.3 B1 — AI-only incident grouper (no pre-filter). Compares extracted incidents from all processed documents and groups them by behavioral similarity.
- **Prompt template**: `fb_incident_grouper` (agents/fb_incident_grouper/prompt.md) via `comparator.py`
- **Input data**: All extracted incidents from all documents in the project
- **Output data**: `{groups: [{incident_ids, description, ...}]}`
- **DB Writes**: **`incident_groups`** — creates groups of related incidents
- **DB Reads**: `incident_groups` (raw incidents), `segmentos`, `documentos`
- **Tools**: None (LLM-only)

#### `b2_label_groups` — Pattern Labeler (with SelfRefinement)
- **Agent ID**: `b2` / `b2_label_groups`
- **What it does**: F2.3 B2 — labels incident groups with codes. Uses SelfRefinementLoop (PRO generate + FLASH critic). Each concept is refined individually until quality checks pass.
- **Prompt template**: `fb_pattern_labeler` (agents/fb_pattern_labeler/prompt.md) for generation, `fb_label_critic` (agents/fb_label_critic/prompt.md) for critique
- **Input data**: Incident groups (from B1), existing codes, `coding_style_instruction`
- **Output data**: `{labels: [{group_id, code_name, definition, ...}]}`
- **DB Writes**: **`categorias`** — inserts new code categories: `id`, `proyecto_id`, `nombre`, `definicion`, `version`. **`codigos_segmento`** — links codes to segments (grounding)
- **DB Reads**: `incident_groups`, `categorias` (existing), `segmentos`
- **Tools**: None (uses SelfRefinementLoop with LLM)

#### `b2_5_assign_codes_to_segments` — Grounding
- **Agent ID**: `grounding` (step name in pipeline)
- **What it does**: Assigns codes to segments (grounding evidence). Uses RAG to find best-matching segments for each code definition, then assigns `codigos_segmento` links.
- **Prompt template**: `fb_evidence_classifier` (agents/fb_evidence_classifier/prompt.md) — via `agents_b.py`
- **Input data**: All codes (from B2), all segments (from documents)
- **Output data**: Segment-code assignments
- **DB Writes**: **`codigos_segmento`** — `id`, `categoria_id`, `segmento_id`, `documento_id` (indirectly via segmentos)
- **DB Reads**: `categorias`, `segmentos`, `documentos`
- **Tools**: RAG search

#### `b3_generate_hypotheses` — Hypothesis Generator
- **Agent ID**: `b3` / `b3_generate_hypotheses`
- **What it does**: Generates hypotheses from incident groups and labeled codes.
- **Prompt template**: `fb_hypothesis_generator` (agents/fb_hypothesis_generator/prompt.md) via `agents_b.py`
- **Input data**: Incident groups, labeled codes, existing hypotheses
- **Output data**: `{hypotheses: [{text, level, confidence, evidence}]}`
- **DB Writes**: **`hypotheses`** — `id`, `project_id`, `text`, `level`, `confidence`, `status`, `concern_labels`, `creado_en`
- **DB Reads**: `incident_groups`, `categorias`, `hypotheses` (existing)
- **Tools**: None

#### `synthesize_categories` — Category Synthesizer
- **Agent ID**: `synthesizer` (internal)
- **What it does**: Merges new categories from current 3-doc batch with previous categories. Uses `fd_category_synthesizer` (PRO) to produce a unified deduplicated set. Dispatched asynchronously after each batch.
- **Prompt template**: `fd_category_synthesizer` (agents/fd_category_synthesizer/prompt.md) via `synthesizer.py`
- **Input data**: New categories (current batch, docs ≥ batch_start), previous categories (docs < batch_start)
- **Output data**: Merged/deduplicated category set
- **DB Writes**: **`categorias`** — updates/merges categories. May insert new, update existing, or mark duplicates.
- **DB Reads**: `categorias`, `incident_groups`
- **Tools**: None (LLM-only)

#### `update_hypotheses` — Recurring Hypotheses
- **Agent ID**: `update_hypotheses_incremental`
- **What it does**: Updates cross-category relationship notes after each synthesizer run. Grows over time as more batches are processed.
- **Prompt template**: `fd_hypothesis_synthesizer` (agents/fd_hypothesis_synthesizer/prompt.md) via `agents_b.py`
- **Input data**: All hypotheses memos, all categories with indicators, document mappings
- **Output data**: Updated relationship notes
- **DB Writes**: **`memos`** — updates/adds hypothesis memos. **`hypotheses`** — may update existing.
- **DB Reads**: `memos`, `categorias`, `hypotheses`, `documentos`
- **Tools**: None

#### `critique_configuration` — Configuration Critic
- **Agent ID**: `config_critic`
- **What it does**: Reviews emerging theoretical configuration after every 3-doc batch (post-synthesizer). Evaluates concerns, population reconfigurations, and coding style adequacy.
- **Prompt template**: `fd_config_critic` (agents/fd_config_critic/prompt.md) via `config_critic.py`
- **Input data**: All categories (with incident/doc counts), all hypotheses
- **Output data**: Critique and suggestions
- **DB Writes**: **`memos`** (critique memos). May suggest updates to project config.
- **DB Reads**: `categorias`, `incident_groups`, `hypotheses`, `codigos_segmento`
- **Tools**: None

---

### 1.4 Synthesis & Cross-Document Agents (Stage 2→3 Bridge)

#### `util_map_synthesis` — Per-Document Map Synthesis
- **Agent ID**: `util_map_synthesis`
- **What it does**: Synthesizes codes within a single document (map phase of map-reduce). Generates per-document summaries for each code.
- **Prompt template**: `util_map_synthesis` (agents/util_map_synthesis/prompt.md)
- **Input data**: Codes + segments from one document
- **Output data**: Per-code document summary
- **DB Writes**: **`code_document_summaries`** — `code_id`, `documento_id`, `summary`
- **DB Reads**: `categorias`, `codigos_segmento`, `segmentos`
- **Tools**: None

#### `util_reduce_synthesis` — Cross-Document Reduce Synthesis
- **Agent ID**: `util_reduce_synthesis`
- **What it does**: Synthesizes per-document code summaries into a consolidated global summary for each code (reduce phase of map-reduce).
- **Prompt template**: `util_reduce_synthesis` (agents/util_reduce_synthesis/prompt.md)
- **Input data**: All per-document summaries for a code
- **Output data**: Consolidated global summary
- **DB Writes**: **`code_global_summaries`** — `code_id`, `summary`
- **DB Reads**: `code_document_summaries`
- **Tools**: None

---

### 1.5 Selective Coding Agents (Stage 3)

These run in the `selective_coding_coordinator` Celery task on the `heavy` queue.

#### `task_main_concern_pipeline` — Core Concern Detection (Phase A, Steps A1+A2)
- **Agent IDs**: `main_concern_proposer` → `main_concern_critic` → HITL gate `pattern_of_interest`
- **What it does**: PRO proposer generates core concern candidates (Core Pattern of Interest), PRO critic evaluates them with feedback (no verdict), then HITL gate pauses for researcher decision.
- **Prompt templates**: `fc_main_concern_proposer` (agents/fc_main_concern_proposer/prompt.md), `fc_main_concern_critic` (agents/fc_main_concern_critic/prompt.md)
- **Input data**: All codes (nombre, definicion), memos (HIPOTESIS, PROPIEDAD, RELACION), prime movers per document, `object_of_study`, `research_question`, `operational_question`, `coding_style_instruction`, `processing_verb`, `processing_gerund`
- **Output data**: `{candidates: [{statement, supporting_codes, orphan_codes, is_latent, rationale}], rationale, no_clear_concern}`
- **DB Writes**: **`hitl_decisions`** — `id`, `project_id`, `gate_name`='pattern_of_interest', `proposal` (JSONB), `critic_verdict` (JSONB), `status`='pending'
- **DB Reads**: `categorias`, `memos`, `document_processes`, `hitl_decisions` (check existing), `proyectos`
- **Tools**: None

#### `task_core_emergence_pipeline` — Core Category Emergence (Phase A, Steps A3+A4)
- **Agent IDs**: `core_emergence_proposer` → `core_emergence_critic` → HITL gate `core_category`
- **What it does**: SQL selects top 3 categories by hypothesis connections, PRO evaluates them qualitatively (centrality, explanatory power, theoretical grab), FLASH critic evaluates interchangeability of incidents, then HITL gate.
- **Prompt templates**: `fc_core_category_proposer` (agents/fc_core_category_proposer/prompt.md), `fc_core_emergence_critic` (agents/fc_core_emergence_critic/prompt.md)
- **Input data**: Top 3 SQL candidates, confirmed concern (from HITL), all categories, hypothesis summary, code statistics (segments/docs)
- **Output data**: `{core_category_candidates: [{category_label, is_central, has_explanatory_power, ...}], recommendation, no_suitable_core}`
- **DB Writes**: **`hitl_decisions`** — `gate_name`='core_category'. **`categorias`** — updates `es_central` flag on confirmed core categories.
- **DB Reads**: `categorias`, `hypotheses`, `hitl_decisions`, `codigos_segmento`, `proyectos`
- **Tools**: None

#### `task_selective_reduction_pipeline` — Selective Reduction (Phase B)
- **Agent IDs**: `selective_reduction_proposer` → `selective_reduction_critic` → HITL gate `selective_reduction`
- **What it does**: Proposes which categories to elevate, which to demote, and which to merge. Reduces the code set to the most theoretically relevant categories.
- **Prompt templates**: `fd_selective_reduction_proposer` (agents/fd_selective_reduction_proposer/prompt.md), `fd_selective_reduction_critic` (agents/fd_selective_reduction_critic/prompt.md)
- **Input data**: All categories, core concern, core category, hypotheses
- **Output data**: Reduction proposal with categories to keep/merge/drop
- **DB Writes**: **`hitl_decisions`** — `gate_name`='selective_reduction'. **`categorias`** — may mark categories, update properties.
- **DB Reads**: `categorias`, `hypotheses`, `hitl_decisions`
- **Tools**: None

#### `task_core_saturation_loop` — Core Saturation (Phase C)
- **Agent IDs**: `core_saturation_proposer` → `core_saturation_critic` → HITL gate `core_saturation`
- **What it does**: Iterative saturation analysis for core categories. Uses `_compute_saturation_panel()` to calculate rolling std, documents-since-change, paradigm state. Continues until all core categories achieve saturation (5 iterations without expansion).
- **Prompt templates**: `fe_core_saturation_proposer` (agents/fe_core_saturation_proposer/prompt.md), `fe_core_saturation_critic` (agents/fe_core_saturation_critic/prompt.md)
- **Input data**: Core categories, paradigm states, saturation metrics
- **Output data**: `{categories_processed, total_expansions, saturation_status}`
- **DB Writes**: **`saturation_metrics`** — `code_id`, `rolling_std`, `saturation_status`, `documents_since_change`. **`paradigm_states`** — `id`, `code_id`, `proyecto_id`, `iteration`, `did_state_expand`, `expansion_type`, `paradigm_snapshot`, `integration_memo`
- **DB Reads**: `categorias`, `paradigm_states`, `saturation_metrics`, `codigos_segmento`, `segmentos`
- **Tools**: `SelectiveElaborator` (service), `EmergentSampler` (service), `RenameDetector` (service)

#### `task_database_a_pipeline` — Database A (Phase D, Step 1)
- **Agent IDs**: `database_a_proposer` → `database_a_critic` → HITL gate `database_a`
- **What it does**: Proposes the first theoretical database organization (Process, Conditions, Variation). Maps categories to theoretical codes from the 6C family.
- **Prompt templates**: `ff_database_a_proposer` (agents/ff_database_a_proposer/prompt.md), `ff_database_a_critic` (agents/ff_database_a_critic/prompt.md)
- **Input data**: All categories, theoretical codes, core concern
- **Output data**: Database A proposal with category groupings
- **DB Writes**: **`hitl_decisions`** — `gate_name`='database_a'. **`conceptual_relationships`** — `id`, `project_id`, `category_ids` (JSONB), `theoretical_code_id`, `researcher_question`, `elaboration_status`, `converging_doc_count`, `diverging_doc_count`, `conceptual_fit`, `layer`, `position_tension`
- **DB Reads**: `categorias`, `theoretical_codes`, `hitl_decisions`
- **Tools**: None

#### `task_database_b_pipeline` — Database B (Phase D, Step 2)
- **Agent IDs**: `database_b_proposer` → `database_b_critic` → HITL gate `database_b`
- **What it does**: Proposes the second theoretical database organization (Structure, Consequences, Action, Fusion). Completes the full 7-layer theoretical architecture.
- **Prompt templates**: `ff_database_b_proposer` (agents/ff_database_b_proposer/prompt.md), `ff_database_b_critic` (agents/ff_database_b_critic/prompt.md)
- **Input data**: Database A results, remaining categories, theoretical codes
- **Output data**: Database B proposal
- **DB Writes**: **`hitl_decisions`** — `gate_name`='database_b'. **`conceptual_relationships`** — additional relationships for layers 4-7
- **DB Reads**: `categorias`, `theoretical_codes`, `conceptual_relationships`, `hitl_decisions`
- **Tools**: None

#### `task_global_saturation_check` — Global Saturation (Phase E)
- **Agent IDs**: Global saturation proposer → HITL gate `global_saturation`
- **What it does**: Final check — verifies that all 7 theoretical layers are covered, all core categories are saturated, and the overall theory is coherent.
- **Prompt templates**: `ff_interchangeability_tester` (agents/ff_interchangeability_tester/prompt.md) and related
- **Input data**: All conceptual relationships, saturation metrics, paradigm states
- **Output data**: Global saturation verdict
- **DB Writes**: **`hitl_decisions`** — `gate_name`='global_saturation'
- **DB Reads**: `conceptual_relationships`, `saturation_metrics`, `paradigm_states`, `categorias`
- **Tools**: None

---

### 1.6 Theoretical Coding Agents (Stage 4)

These run in the Theoretical Playground (post selective coding, post Database A/B).

#### `ElaborationEngine` — Conceptual Elaboration (`elaboration_engine.py`)
- **Agent ID**: `elaboration_engine`
- **What it does**: Orchestrates conceptual relationship elaboration. Loads categories with incidents, theoretical code evaluation logic, invokes PRO to evaluate relationships, creates `ConceptualRelationship` + `ElaborationMemo`. Handles divergence expansion and ghost-blob absorption.
- **Prompt template**: `f6b_conceptual_elaborator` (agents/f6b_conceptual_elaborator/prompt.md)
- **Input data**: `category_ids`, `theoretical_code_id`, `researcher_question`
- **Output data**: `ElaborationResult(relationship_id, elaboration_status, conceptual_fit, converging_count, diverging_count, summary, diverging_incidents)`
- **DB Writes**: **`conceptual_relationships`** — inserts new relationships. **`elaboration_memos`** — inserts `relationship_proposed`, `divergence_expanded` memos. **`category_definition_versions`** — version history when ghost-blob absorbed
- **DB Reads**: `categorias`, `codigos_segmento`, `segmentos`, `documentos`, `theoretical_codes`, `memos`
- **Tools**: None (LLM-only)

#### `SelectiveElaborator` — Incident Elaboration (`selective_elaborator.py`)
- **Agent ID**: `selective_elaborator`
- **What it does**: S05 of Selective Coding. Iterative cycle evaluating each incident against a category's current state. Detects convergence (incident fits) vs divergence (incident expands the category). Updates `paradigm_states` and may expand definition, suggest rename.
- **Prompt template**: `f6b_incident_elaborator` (agents/f6b_incident_elaborator/prompt.md)
- **Input data**: `category_id`, `incident_text`, `document_name`
- **Output data**: `ElaborationResult(category_id, elaboration_type: "converges"|"diverges_dimension"|"diverges_property"|"diverges_condition"|"diverges_strong", description, expanded_definition, new_properties, suggested_action, rename_suggested, rename_candidates)`
- **DB Writes**: **`paradigm_states`** — `id`, `code_id`, `proyecto_id`, `iteration`, `did_state_expand`, `expansion_type`, `paradigm_snapshot`, `integration_memo`. **`categorias`** — updates `definicion`, `version`, `metadatos` (rename_pending, rename_candidates). **`category_definition_versions`** — version history
- **DB Reads**: `categorias`, `paradigm_states`, `proyectos`
- **Tools**: None (LLM-only)

#### `GhostConnector` — Ghost-Blob Mapper (`ghost_connector.py`)
- **Agent ID**: `ghost_connector`
- **What it does**: T26 — connects orphaned hypothesis memos (ghost-blobs) with categories for the Theoretical Playground. Classifies memos and suggests target categories or new category creation.
- **Prompt template**: `f6b_ghost_blob_mapper` (agents/f6b_ghost_blob_mapper/prompt.md)
- **Input data**: Orphaned memos (`tipo='HIPOTESIS'`, not yet absorbed), existing categories (score ≥ 3), core concern
- **Output data**: `[{id, disposition: "mapped"|"unmapped"|"suggest_new", target_category_ids, what_it_adds, suggested_new_category?, position}]`
- **DB Writes**: None directly (absorptions delegated to `ElaborationEngine.absorb_ghost_blob()`). **`elaboration_memos`** — when ghost is absorbed. **`category_definition_versions`** — version history on absorption
- **DB Reads**: `memos`, `elaboration_memos`, `categorias`, `proyectos`
- **Tools**: None (LLM-only)

#### `RenameDetector` — Rename Suggester (`rename_detector.py`)
- **Agent ID**: `rename_detector`
- **What it does**: Detects when a category should be renamed (≥3 definition versions, property growth ≥2x, incident growth ≥3x). Generates rename candidates via PRO. Applies confirmed renames with version history.
- **Prompt template**: `f6b_rename_suggester` (agents/f6b_rename_suggester/prompt.md)
- **Input data**: Category name, definition, version, original name/definition, properties growth, incident count, core concern, `coding_style_instruction`
- **Output data**: `{category_id, current_name, suggestions: [{name, style_used, rationale}]}` or None if name is adequate
- **DB Writes**: **`categorias`** — `nombre`, `version`. **`category_definition_versions`** — new version entry with trigger `rename_applied`
- **DB Reads**: `categorias`, `category_definition_versions`, `codigos_segmento`, `proyectos`
- **Tools**: None (LLM-only)

#### `RecommendationEngine` — Playground Recommendations (`recommendation_engine.py`)
- **Agent ID**: `recommendation_engine`
- **What it does**: T13 — generates actionable recommendations for advancing theory: (1) suggested connections, (2) ghost absorption, (3) renames, (4) sampling zones, (5) tension resolution. Pure SQL + heuristics (no LLM).
- **Prompt template**: None (pure SQL logic)
- **Input data**: Project ID only
- **Output data**: `[Recommendation(category, title, description, action_type, category_ids, suggested_code, impact_score)]`
- **DB Writes**: None (read-only)
- **DB Reads**: `categorias`, `codigos_segmento`, `segmentos`, `conceptual_relationships`, `memos`, `elaboration_memos`, `category_definition_versions`, `ecosystem_layouts`
- **Tools**: None

#### `SaturationGapAnalyzer` — 4-Source Gap Analysis (`saturation_gap_analyzer.py`)
- **Agent ID**: `saturation_gap_analyzer`
- **What it does**: C08 — unifies 4 gap detection sources: (1) math saturation (rolling std), (2) paradigm state (expansion window), (3) sampling axes (category variable gaps), (4) relationship density (orphaned categories). Pure SQL + heuristics (no LLM).
- **Prompt template**: None (pure SQL logic)
- **Input data**: Project ID
- **Output data**: `GapReport(project_id, critical: [Gap], warnings: [Gap], saturated: [str], generated_at)`
- **DB Writes**: None (read-only)
- **DB Reads**: `categorias`, `saturation_metrics`, `codigos_segmento`, `segmentos`, `paradigm_states`, `conceptual_relationships`
- **Tools**: None

#### `EmergentSampler` — Property-Based Sampling (`emergent_sampler.py`)
- **Agent ID**: `emergent_sampler`
- **What it does**: E03 — theoretical sampling by emergent properties instead of demographics. Detects imbalanced gradients in category dimensions, scans corpus for missing extremes (FLASH), suggests external sampling if needed (PRO).
- **Prompt template**: `fe_corpus_scanner` (FLASH), `fe_property_sampler` (PRO)
- **Input data**: Categories, paradigm states, segments
- **Output data**: `SamplingResult(category_id, property_name, target_extreme, found_incidents, gradient_expanded, corpus_gap, sampling_recommendation, suggested_interview_question)`
- **DB Writes**: None directly (recommendation only)
- **DB Reads**: `categorias`, `paradigm_states`, `codigos_segmento`, `segmentos`
- **Tools**: None (LLM-only)

#### `TheorySeeder` — Built-in Theoretical Codes (`theory_seeder.py`)
- **Agent ID**: `theory_seeder`
- **What it does**: Seeds 12 built-in Glaserian theoretical codes (6C family + process + consequences + conditions + etc.) at DB initialization or project creation. Codes with `project_id=NULL` are global.
- **Prompt template**: None (no LLM — data from `app.core.theoretical_families`)
- **Input data**: None (reads `THEORETICAL_FAMILIES` constant)
- **Output data**: Count of inserted codes
- **DB Writes**: **`theoretical_codes`** — `id`, `project_id`, `name`, `family`, `description`, `glaserian`, `user_defined`, `evaluation_logic` (JSONB), `output_schema` (JSONB), `compatible_with` (JSONB), `layer`, `visualization_hint`
- **DB Reads**: `theoretical_codes` (check existing)
- **Tools**: None

---

### 1.7 Writing & Final Agents (Stage 5)

#### `f6a_final_report` — Final Report Generator
- **Agent ID**: `final_report` (pipeline graph node)
- **What it does**: Generates the final natural-language grounded theory report.
- **Prompt template**: `f6a_final_report` (agents/f6a_final_report/prompt.md)
- **Input data**: All categories, relationships, evidence maps, memos
- **Output data**: Final report text
- **DB Writes**: **`memos`** (report memo). May update project status.
- **DB Reads**: `categorias`, `conceptual_relationships`, `memos`, `ecosystem_layouts`
- **Tools**: None

#### `f6a_natural_writer` — Natural Writer
- **Agent ID**: `natural_writer`
- **What it does**: Writes natural-language prose for theory sections.
- **Prompt template**: `f6a_natural_writer` (agents/f6a_natural_writer/prompt.md)
- **Input data**: Theory structure, evidence, style guidance
- **Output data**: Written text
- **DB Writes**: **`memos`** (writing memos)
- **DB Reads**: Various theory tables
- **Tools**: None

#### `f6a_writing_critic` — Writing Critic
- **Agent ID**: `writing_critic`
- **What it does**: Critiques written output for clarity, theoretical accuracy, evidence grounding.
- **Prompt template**: `f6a_writing_critic` (agents/f6a_writing_critic/prompt.md)
- **Input data**: Written text, evidence references
- **Output data**: Critique with suggestions
- **DB Writes**: None (feedback only)
- **DB Reads**: None
- **Tools**: None

#### `f6a_gap_feeler` — Gap Feeler
- **Agent ID**: `gap_feeler`
- **What it does**: Feels for theoretical gaps in the final theory — missing connections, unexplained phenomena.
- **Prompt template**: `f6a_gap_feeler` (agents/f6a_gap_feeler/prompt.md)
- **Input data**: Full theoretical model
- **Output data**: Gap report
- **DB Writes**: **`memos`** (gap memos)
- **DB Reads**: `conceptual_relationships`, `categorias`
- **Tools**: None

---

### 1.8 HITL & Meta-Agents

#### `hitl_gate` — HITL Gate Function (`transitions.py`)
- **Agent ID**: N/A (utility function)
- **What it does**: Saves a HITL proposal/critic pair as a pending decision, notifies frontend via Redis pub/sub. Pipeline PAUSES here until researcher responds via `POST /projects/{id}/hitl/{gate}/decide`.
- **Prompt template**: None (system function)
- **Gates known**: `pattern_of_interest`, `core_category`, `selective_reduction`, `core_saturation`, `database_a`, `database_b`, `global_saturation`
- **DB Writes**: **`hitl_decisions`** — `id`, `project_id`, `gate_name`, `proposal` (JSONB), `critic_verdict` (JSONB), `status`='pending'
- **DB Reads**: None directly (insert only)
- **Tools**: None (notifies via Redis)

#### `f6b_memo_theoretical_tagger` — Memo Theoretical Tagger
- **Agent ID**: `memo_theoretical_tagger`
- **What it does**: Tags all memos with theoretical coding families when entering the Playground. Maps memo content to theoretical categories (6C family, process, conditions, etc.).
- **Prompt template**: `f6b_memo_theoretical_tagger` (agents/f6b_memo_theoretical_tagger/prompt.md)
- **Input data**: Memo content, theoretical code families
- **Output data**: Tagged memo with family assignment
- **DB Writes**: **`memos`** — updates with theoretical family tags
- **DB Reads**: `memos`, `theoretical_codes`
- **Tools**: None

#### `f6b_ecosystem_gap_detector` — Ecosystem Gap Detector
- **Agent ID**: `ecosystem_gap_detector`
- **What it does**: Detects gaps in the ecosystem layout — unlinked ghost blobs, empty fog zones, missing theoretical layers.
- **Prompt template**: `f6b_ecosystem_gap_detector` (agents/f6b_ecosystem_gap_detector/prompt.md)
- **Input data**: Ecosystem layout, ghost blobs, conceptual relationships
- **Output data**: Gap detection results
- **DB Writes**: May update ecosystem layout
- **DB Reads**: `ecosystem_layouts`, `ghost_blobs`, `conceptual_relationships`
- **Tools**: None

#### `f6b_gap_alerter` — Gap Alerter (PRO)
- **Agent ID**: `gap_alerter`
- **What it does**: Dispatched when ≥3 unlinked ghost blobs detected. Alerts researcher with gap summary.
- **Prompt template**: `f6b_gap_alerter` (agents/f6b_gap_alerter/prompt.md)
- **Input data**: `core_concern`, `object_of_study`, `gaps_summary`
- **Output data**: Alert content
- **DB Writes**: None (log/notification only)
- **DB Reads**: None
- **Tools**: None

---

### 1.9 Utility & Auxiliary Agents

#### Segmentor — `segmentar_documento` (NLP worker)
- **Agent ID**: N/A (Celery task on `nlp` queue)
- **What it does**: Progressive text segmentation using Reinert method + TEI embeddings. Segments text, persists segments with embeddings (pgvector), marks document as `segmentado`, transitions pipeline.
- **Prompt template**: None (algorithmic)
- **Input data**: `texto`, `max_tokens` (1024), `doc_title`, `source_type`, `global_summary`, `documento_id`
- **Output data**: `{num_segmentos, inserted}`
- **DB Writes**: **`segmentos`** — `id`, `documento_id`, `texto`, `posicion`, `conteo_tokens`, `es_anomalia`, `embedding` (pgvector). **`documentos`** — `estado` transitions: `crudo→segmentando→segmentado`
- **DB Reads**: `documentos` (proyecto_id lookup)
- **Tools**: TEI embeddings (voyage-4-nano-ONNX)

#### Punctuator — `punctuate_text` (FAST worker)
- **Agent ID**: N/A (Celery task on `fast` queue)
- **What it does**: Adds punctuation to raw text (e.g., interview transcripts without punctuation) before segmentation.
- **Prompt template**: `util_punctuator` (agents/util_punctuator/prompt.md)
- **Input data**: Raw text
- **Output data**: Punctuated text
- **DB Writes**: None (returns text to caller)
- **DB Reads**: None
- **Tools**: None (LLM-only)

#### `population_generalizer` — Population Generalizer (FAST worker)
- **Agent ID**: `population_generalizer`
- **What it does**: Generalizes population characteristics from document data.
- **Prompt template**: `f0_population_generalizer` (agents/f0_population_generalizer/prompt.md)
- **Input data**: Population context, documents
- **Output data**: Generalized population statement
- **DB Writes**: **`proyectos`** — may update `population_assumption`
- **DB Reads**: `population_contexts`, `documentos`
- **Tools**: None

#### `util_code_namer` — Code Namer
- **Agent ID**: `code_namer`
- **What it does**: Suggests code names using gerundio/in-vivo/nominalization styles.
- **Prompt template**: `util_code_namer` (agents/util_code_namer/prompt.md)
- **Input data**: Code definition, coding style
- **Output data**: `{suggestions: [{name, style_used, rationale}]}` — max 3 suggestions
- **DB Writes**: None (suggestion only)
- **DB Reads**: None
- **Tools**: None

#### `util_code_critic` — Code Critic
- **Agent ID**: `code_critic`
- **What it does**: Critiques codes for quality (style, definition, grounding, redundancy).
- **Prompt template**: `util_code_critic` (agents/util_code_critic/prompt.md)
- **Input data**: Codes to critique
- **Output data**: `{all_valid, issues: [{code_name, problem, suggestion}]}`
- **DB Writes**: None (critique only)
- **DB Reads**: None
- **Tools**: Algorithmic scorer for pre-filter

#### `util_theme_grouper` — Theme Grouper
- **Agent ID**: `theme_grouper`
- **What it does**: Groups codes into themes with indicators and suggested gerund names.
- **Prompt template**: `util_theme_grouper` (agents/util_theme_grouper/prompt.md)
- **Input data**: Codes with definitions
- **Output data**: `{themes: [{name, indicators, suggested_gerundio}]}`
- **DB Writes**: None (grouping suggestion)
- **DB Reads**: None
- **Tools**: None

#### `util_recategorization_decider` — Recategorization Decider
- **Agent ID**: `recategorization_decider`
- **What it does**: Decides whether codes should be recategorized — merge, split, or rename.
- **Prompt template**: `util_recategorization_decider` (agents/util_recategorization_decider/prompt.md)
- **Input data**: Codes with overlap analysis
- **Output data**: Recategorization decisions
- **DB Writes**: Potentially updates `categorias`
- **DB Reads**: `categorias`, `compare_tools`
- **Tools**: `compare_embeddings`, `find_similar_codes`

#### `util_entity_extraction` — Entity Extractor
- **Agent ID**: `entity_extractor`
- **What it does**: Extracts named entities and graph entities from text.
- **Prompt template**: `util_entity_extraction` (agents/util_entity_extraction/prompt.md)
- **Input data**: Text segments
- **Output data**: Extracted entities
- **DB Writes**: None (output to caller)
- **DB Reads**: None
- **Tools**: None

#### `util_react_hypothesis` — React Hypothesis
- **Agent ID**: `react_hypothesis`
- **What it does**: Interactive hypothesis generation/refinement using ReAct pattern.
- **Prompt template**: `util_react_hypothesis` (agents/util_react_hypothesis/prompt.md)
- **Input data**: Current hypotheses, evidence
- **Output data**: Refined hypothesis
- **DB Writes**: **`hypotheses`**
- **DB Reads**: `hypotheses`, `categorias`
- **Tools**: `get_existing_hypotheses`, `search_segments`

#### `incident_extractor` — Legacy Incident Extractor (DEPRECATED)
- **Agent ID**: `incident_extractor`
- **What it does**: Was per-segment incident extraction. Now replaced by `extract_patterns_and_incidents` (unified F2.3 PRO call).
- **Prompt template**: `incident_extractor` (agents/incident_extractor/prompt.md)
- **Status**: Deprecated — kept for backward compatibility

#### `memo_generator` / `memo_correlator` / `memo_simplifier`
- **Agent IDs**: `memo_generator`, `memo_correlator`, `memo_simplifier`
- **What they do**: Memo generation, correlation between memos, and simplification/consolidation of memos.
- **Prompt templates**: `memo_generator`, `memo_correlator`, `memo_simplifier` (agents/ directory)
- **DB Writes**: **`memos`**
- **DB Reads**: `memos`, `categorias`
- **Tools**: None

#### `pattern_labeler` — Pattern Labeler
- **Agent ID**: `pattern_labeler`
- **What it does**: Labels behavioral patterns with codes. Related to B2 labeling.
- **Prompt template**: `pattern_labeler` (agents/pattern_labeler/prompt.md)
- **DB Writes**: **`categorias`**, **`codigos_segmento`**
- **DB Reads**: `segmentos`, `categorias`
- **Tools**: None

#### Context Window Agents (CWM)
- **Agent IDs**: `cwm_map_grouper`, `cwm_react_explorer`, `cwm_reduce_merger`
- **What they do**: Context window management — batch map-reduce for large corpora. `cwm_map_grouper` groups related segments, `cwm_react_explorer` explores context interactively, `cwm_reduce_merger` merges findings.
- **Prompt templates**: `cwm_map_grouper`, `cwm_react_explorer`, `cwm_reduce_merger` (agents/ directory)
- **Tools used by**: `batch_map_reduce`, `expand_incident`, `search_precise_entities`, `get_document_window` (in `context_window.py`)
- **DB Writes**: None directly (in-memory/return to caller)
- **DB Reads**: `segmentos`, `documentos` (via tools)
- **Tools**: All CWM tool functions

#### `definition_writer` — Definition Writer
- **Agent IDs**: `definition_writer`, `f6b_definition_writer`
- **What they do**: Write and refine category definitions.
- **Prompt templates**: `definition_writer`, `f6b_definition_writer` (agents/ directory)
- **DB Writes**: **`categorias`** — `definicion`, `version`
- **DB Reads**: `categorias`, `codigos_segmento`
- **Tools**: None

#### Literature Agents (F6c)
- **Agent IDs**: `f6c_literature_comparer`, `f6c_literature_critic`
- **What they do**: Compare emergent theory with existing literature. Proposer generates comparisons, critic evaluates them.
- **Prompt templates**: `f6c_literature_comparer`, `f6c_literature_critic` (agents/ directory)
- **DB Writes**: **`memos`**
- **DB Reads**: `categorias`, `conceptual_relationships`
- **Tools**: Search tools

#### Applicability Agents (F6d)
- **Agent IDs**: `f6d_applicability_engine`, `f6d_applicability_critic`
- **What they do**: Evaluate practical applicability of the theory. Engine proposes applications, critic evaluates feasibility.
- **Prompt templates**: `f6d_applicability_engine`, `f6d_applicability_critic` (agents/ directory)
- **DB Writes**: **`memos`**
- **DB Reads**: `categorias`, `conceptual_relationships`
- **Tools**: None

#### `agrupador` / `ff_agrupador` — Group Builder
- **Agent IDs**: `agrupador`, `ff_agrupador`, `ff_clusterizador_informado`
- **What they do**: Group/merge related codes. `clusterizador_informado` uses informed clustering.
- **Prompt templates**: `agrupador`, `ff_agrupador`, `ff_clusterizador_informado` (agents/ directory)
- **DB Writes**: **`categorias`** (merging)
- **DB Reads**: `categorias`, `codigos_segmento`
- **Tools**: `compare_embeddings`, `find_similar_codes`

#### `prime_mover_extractor` — Prime Mover Extractor
- **Agent IDs**: `prime_mover_extractor`, `fa_prime_mover_extractor`
- **What they do**: Extract the prime mover (main behavioral driver) from document segments.
- **Prompt templates**: `prime_mover_extractor`, `fa_prime_mover_extractor` (agents/ directory)
- **DB Writes**: **`document_processes`** — `prime_mover`, `prime_mover_confidence`
- **DB Reads**: `segmentos`
- **Tools**: None

---

## Section 2: Pipeline Stage Data Flow

### Stage 1: Data Management

| Aspect | Detail |
|--------|--------|
| **Celery Task** | `process_document_agents_a` (heavy queue, 1 doc at a time) |
| **Trigger** | `segmentado → procesando → listo` transition chain |
| **Agents Run** | `_classify_glaser_types_for_doc`, `extract_patterns_and_incidents`, `a1_build_population_context`, `a2_identify_process`, `a3_make_sense` |
| **Data Produced** | `glaser_type` on segments, `incident_groups` (extracted patterns/incidents), `population_contexts` (v1+ per batch), `document_processes` (process_description, prime_mover, sense_status), `memos` (hypothesis memos from A3) |
| **DB Write Tables** | `segmentos`, `document_processes`, `population_contexts`, `memos`, `incident_groups` |
| **HITL Gates** | None at this stage |
| **Orchestrator Role** | Dispatches ONE `segmentar_documento` and ONE `process_document_agents_a` at a time. Sequential per doc. |

### Stage 2: Open Coding

| Aspect | Detail |
|--------|--------|
| **Celery Task** | `process_synthesis_agents_b` (heavy queue, project-level, triggered when ≥3 docs = `listo`) |
| **Trigger** | `_maybe_trigger_phase_b()` when ≥3 docs `listo` — dispatches `process_synthesis_agents_b` |
| **Agents Run** | B1 `b1_group_incidents`, B2 `b2_label_groups` (SelfRefinement), B2.5 `b2_5_assign_codes_to_segments` (grounding), B3 `b3_generate_hypotheses`. Then async: `synthesize_categories`, `update_hypotheses`, `critique_configuration` |
| **Data Produced** | `incident_groups` (grouped incidents), `categorias` (new codes with nombre, definicion), `codigos_segmento` (code-segment grounding assignments), `hypotheses` (text, level, confidence, concern_labels), `code_document_summaries`, `code_global_summaries` (via map-reduce) |
| **DB Write Tables** | `incident_groups`, `categorias`, `codigos_segmento`, `hypotheses`, `memos`, `code_document_summaries`, `code_global_summaries`, `saturation_metrics` (via update_saturation) |
| **HITL Gates** | `pause_mode='manual'` → Redis `batch_ready` event, pipeline pauses, researcher continues manually. `pause_mode='auto'` → auto-dispatch. |
| **Orchestrator Role** | Deduplicates Phase B via `processing_states` step marker. Transition docs `listo → sintetizado` after successful batch. Triggers `_maybe_trigger_selective_coding` when all docs `sintetizado`. Triggers `_maybe_trigger_iteration` for new docs in advanced projects. |

### Stage 3: Selective Coding

| Aspect | Detail |
|--------|--------|
| **Celery Task** | `selective_coding_coordinator` (heavy queue, project-level) |
| **Trigger** | `_maybe_trigger_selective_coding()` when all docs `sintetizado` |
| **Agents Run** | Phase A: `task_main_concern_pipeline` (proposer + critic + HITL `pattern_of_interest`), `task_core_emergence_pipeline` (proposer + critic + HITL `core_category`). Phase B: `task_selective_reduction_pipeline` (proposer + critic + HITL `selective_reduction`). Phase C: `task_core_saturation_loop` (iterative saturation with `SelectiveElaborator`, `EmergentSampler`, `RenameDetector`). |
| **Data Produced** | Core concern candidates, core category candidates, reduction proposals, saturation metrics, paradigm states, expanded category definitions, rename suggestions |
| **DB Write Tables** | `hitl_decisions` (all gates), `categorias` (es_central, definicion updates, rename, metadatos), `saturation_metrics`, `paradigm_states`, `category_definition_versions`, `memos` |
| **HITL Gates** | **5 gates**: `pattern_of_interest`, `core_category`, `selective_reduction`, `core_saturation`, `database_a`, `database_b`, `global_saturation` — each pauses pipeline until researcher confirms |
| **Orchestrator Role** | `transition_project()` advances project state: `coding → finding_cc → reducing → saturating → building_db → playground_ready`. `_maturity_gate()` blocks if <2 related categories or <2 hypotheses. |

### Stage 4: Theoretical Coding

| Aspect | Detail |
|--------|--------|
| **Celery Task** | Tasks dispatched from `selective_coding_coordinator`, plus `_prepare_playground_for_project` |
| **Trigger** | Auto-triggered when project reaches `playground_ready` state |
| **Agents Run** | `task_database_a_pipeline` (proposer + critic + HITL), `task_database_b_pipeline` (proposer + critic + HITL), `task_global_saturation_check`. Then `_prepare_playground_for_project`: seeds theoretical codes, creates ecosystem layout, generates ghost blobs, tags memos, detects gaps. |
| **Data Produced** | `conceptual_relationships` (category-ids, theoretical-code-id, elaboration-status, converging/diverging counts, conceptual-fit), `elaboration_memos`, `ecosystem_layouts` (blob_positions, ghost_positions, fog_zones, physics_params), ghost blobs |
| **DB Write Tables** | `conceptual_relationships`, `elaboration_memos`, `ecosystem_layouts`, `theoretical_codes` (global seed), `memos` (tagged), `hitl_decisions` |
| **HITL Gates** | `database_a`, `database_b`, `global_saturation` |
| **Orchestrator Role** | Manages state machine: `building_db → playground_ready` after all three HITL gates pass. `_maybe_trigger_iteration()` detects new docs added after `playground_ready` and re-triggers synthesis. |

### Stage 5: Writing

| Aspect | Detail |
|--------|--------|
| **Celery Task** | Individual Celery tasks (`task_final_report`, `task_natural_writer`, etc.) |
| **Trigger** | Manual or from playground UI |
| **Agents Run** | `f6a_final_report`, `f6a_natural_writer`, `f6a_writing_critic`, `f6a_gap_feeler`, `f6c_literature_comparer`/`critic`, `f6d_applicability_engine`/`critic` |
| **Data Produced** | Final report text, literature comparison, applicability assessment |
| **DB Write Tables** | `memos` (report/writing memos) |
| **HITL Gates** | `hitl_review` (pre-final report), researcher confirmation required |
| **Orchestrator Role** | `prepare_playground → hitl_review → final_report` via pipeline graph nodes |

---

## Section 3: Service-to-DB Write Map

### `pipeline_orchestrator.py` — PipelineOrchestrator

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| `pipeline_runs` | `id`, `project_id`, `status`, `triggered_by`, `summary` | INSERT | Creates run on `start_pipeline()` |
| `documentos` | `estado` | UPDATE | Transitions `crudo→segmentando`, `segmentado→procesando` |
| `pipeline_tasks` | `id`, `run_id`, `document_id`, `celery_task_id`, `task_name`, `queue`, `status`, `doc_estado_before`, `segments_before`, `codes_before` | INSERT | Tracks each dispatched Celery task |
| `segmentos` | all rows | DELETE | On `force=True` reset |
| `codigos_segmento` | all rows | DELETE | On `force=True` reset (cascading via segmento_id) |
| `processing_states` | all project rows | DELETE | On `force=True` reset |
| `proyectos` | — | READ | Verifies project exists |
| `documentos` | `id`, `estado`, `metadatos` | READ | Counts segments and codes |

### `transitions.py`

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| `documentos` | `estado` | UPDATE | ALL state transitions with optimistic locking |
| `pipeline_tasks` | `id`, `run_id`, `document_id`, `celery_task_id`, `task_name`, `queue`, `status`, `doc_estado_before` | INSERT | Task tracking |
| `proyectos` | `estado` | UPDATE | Project-level state transitions |
| `processing_states` | `entity_type`, `entity_id`, `step` | INSERT | Deduplication markers |
| `hitl_decisions` | `id`, `project_id`, `gate_name`, `proposal`, `critic_verdict`, `status` | INSERT | All HITL gates |
| `documentos` | `estado` | UPDATE | Transition `listo→sintetizado` after synthesis |
| `proyectos` | `pause_mode` | READ | Check before dispatching Phase B |
| `pipeline_runs` | `id` | READ | Get active run |
| `proyectos` | `estado` | READ | Check for iteration trigger |

### `theory_seeder.py`

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| `theoretical_codes` | `id`, `project_id`, `name`, `family`, `description`, `glaserian`, `user_defined`, `evaluation_logic`, `output_schema`, `compatible_with`, `layer`, `visualization_hint` | INSERT | 12 built-in Glaserian codes |

### `selective_elaborator.py` — SelectiveElaborator

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| `paradigm_states` | `id`, `code_id`, `proyecto_id`, `iteration`, `did_state_expand`, `expansion_type`, `paradigm_snapshot`, `integration_memo` | INSERT | New paradigm state per elaboration cycle |
| `categorias` | `definicion`, `version` | UPDATE | When definition expands |
| `categorias` | `metadatos` (JSONB) — `rename_pending`, `rename_candidates` | UPDATE | When rename suggested |
| `categorias` | `nombre`, `definicion`, `version`, `proyecto_id` | READ | Load category state |
| `paradigm_states` | `paradigm_snapshot`, `iteration` | READ | Load current paradigm |
| `proyectos` | `population_assumption` | READ | Get coding style |

### `elaboration_engine.py` — ElaborationEngine

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| `conceptual_relationships` | `id`, `project_id`, `category_ids`, `theoretical_code_id`, `researcher_question`, `elaboration_status`, `converging_doc_count`, `diverging_doc_count`, `conceptual_fit`, `layer`, `position_tension` | INSERT | New relationship |
| `conceptual_relationships` | `divergence_resolution`, `elaboration_status`, `position_tension` | UPDATE | When divergence resolved |
| `elaboration_memos` | `id`, `project_id`, `elaboration_type`, `relationship_id`/`category_id`/`memo_id`, `content` | INSERT | Memos for proposed/expanded/absorbed |
| `category_definition_versions` | `id`, `category_id`, `project_id`, `version`, `name_at_version`, `definition_at_version`, `trigger`, `trigger_detail` | INSERT | Version history on ghost absorption |
| `categorias` | `nombre`, `definicion` | READ | Load category data |
| `codigos_segmento` | `segmento_id`, `categoria_id` | READ | Load incidents |
| `segmentos` | `texto` | READ | Incident text |
| `documentos` | `original_filename` | READ | Document names |
| `theoretical_codes` | `name`, `evaluation_logic`, `layer` | READ | Theoretical lens |
| `memos` | `contenido` | READ | Related memos |

### `ghost_connector.py` — GhostConnector

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| `elaboration_memos` | `id`, `project_id`, `elaboration_type`, `category_id`, `memo_id`, `content` | INSERT | Via `ElaborationEngine.absorb_ghost_blob()` |
| `category_definition_versions` | `id`, `category_id`, `project_id`, `version`, `name_at_version`, `definition_at_version`, `trigger`, `trigger_detail` | INSERT | Via `ElaborationEngine` |
| `memos` | `id`, `contenido`, `tipo` | READ | Find orphan memos |
| `elaboration_memos` | `memo_id` | READ | Check if memo already absorbed |
| `categorias` | `id`, `nombre`, `definicion` | READ | Existing categories |
| `proyectos` | `supuesto_poblacional` | READ | Core concern |

### `recommendation_engine.py` — RecommendationEngine

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| None | — | READ ONLY | All recommendations are read-only queries |

| Table | Read For |
|-------|----------|
| `codigos_segmento` | Co-occurrence analysis |
| `segmentos` | Document counts |
| `categorias` | Category data |
| `conceptual_relationships` | Existing relationships, orphan detection |
| `memos` | Ghost candidates |
| `elaboration_memos` | Absorption check |
| `category_definition_versions` | Version count for rename candidates |

### `saturation_gap_analyzer.py` — SaturationGapAnalyzer

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| None | — | READ ONLY | Analysis only, no writes |

| Table | Read For |
|-------|----------|
| `categorias` | Code names, project filter |
| `saturation_metrics` | Rolling std, saturation_status, documents_since_change |
| `paradigm_states` | Expansion window (5-iteration check) |
| `codigos_segmento` | Segment counts per category |
| `conceptual_relationships` | Relationship density, orphan detection |

### `rename_detector.py`

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| `categorias` | `nombre`, `version` | UPDATE | Apply rename |
| `category_definition_versions` | `id`, `category_id`, `project_id`, `version`, `name_at_version`, `definition_at_version`, `trigger`, `trigger_detail` | INSERT | New version on rename |
| `categorias` | `nombre`, `definicion`, `version` | READ | Current state |
| `category_definition_versions` | `version`, `properties_at_version`, `incident_count_at_version`, `name_at_version`, `definition_at_version` | READ | Growth analysis |
| `codigos_segmento` | `COUNT(*)` | READ | Incident count |
| `proyectos` | `supuesto_poblacional`, `population_assumption` | READ | Core concern, coding style |

### `emergent_sampler.py` — EmergentSampler

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| None | — | READ ONLY | Sampling recommendations only, no writes |

| Table | Read For |
|-------|----------|
| `categorias` | Category names, definitions |
| `paradigm_states` | Property dimensions, gradients |
| `codigos_segmento` | Incident counts per extreme |
| `segmentos` | Corpus scanning for target extremes |
| `documentos` | Document names |

### `rag.py` — RAGService

| Table | Column(s) | Operation | Notes |
|-------|-----------|-----------|-------|
| None | — | READ ONLY | Search service, no writes |

| Table | Read For |
|-------|----------|
| `segmentos` | `texto`, `embedding` (pgvector) — semantic/lexical search |
| `documentos` | `original_filename` — result metadata |
| `categorias` | `embedding_centroide` — code similarity search |

### Worker Tasks — DB Write Summary

#### NLP Worker (`segmentar_documento`)

| Table | Column(s) | Operation |
|-------|-----------|-----------|
| `segmentos` | `id`, `documento_id`, `texto`, `posicion`, `conteo_tokens`, `es_anomalia`, `embedding` | INSERT |
| `documentos` | `estado` | UPDATE (`segmentando`, `segmentado`) |
| `segmentos` | DELETE | Remove old segmentos (re-segmentation) |
| `documentos` | `estado='error'` | UPDATE (on failure) |

#### Heavy Worker (`process_document_agents_a`)

| Table | Column(s) | Operation |
|-------|-----------|-----------|
| `population_contexts` | `id`, `proyecto_id`, `surprising_details`, `language_patterns`, `data_production_context`, `source_document_ids`, `version` | INSERT |
| `document_processes` | `id`, `documento_id`, `proyecto_id`, `process_description`, `similarity_to_previous`, `difference_from_previous` | INSERT/UPDATE |
| `memos` | `id`, `proyecto_id`, `tipo`, `contenido` | INSERT (HIPOTESIS from A3) |
| `hypotheses` | `id`, `project_id`, `text`, `level`, `confidence`, `status`, `concern_labels` | INSERT |
| `segmentos` | `glaser_type` | UPDATE (classification) |
| `documentos` | `estado` | UPDATE (`procesando`) |
| `incident_groups` | — | INSERT (via pattern_extractor) |

#### Heavy Worker (`process_synthesis_agents_b`)

| Table | Column(s) | Operation |
|-------|-----------|-----------|
| `incident_groups` | — | INSERT/UPDATE (grouping) |
| `categorias` | `id`, `proyecto_id`, `nombre`, `definicion`, `version` | INSERT |
| `codigos_segmento` | `id`, `categoria_id`, `segmento_id` | INSERT (grounding) |
| `hypotheses` | `id`, `project_id`, `text`, `level`, `confidence`, `status`, `concern_labels` | INSERT |
| `saturation_metrics` | `code_id`, `rolling_std`, `saturation_status`, `documents_since_change` | UPSERT |
| `memos` | — | INSERT (hypothesis notes) |
| `code_document_summaries` | `code_id`, `documento_id`, `summary` | INSERT (via synthesizer) |
| `code_global_summaries` | `code_id`, `summary` | INSERT (via synthesizer) |
| `categorias` | `definicion`, `nombre` | UPDATE (via synthesizer) |
| `documentos` | `estado='sintetizado'` | UPDATE (after successful batch) |

#### Heavy Worker (`selective_coding_coordinator`)

| Table | Column(s) | Operation |
|-------|-----------|-----------|
| `hitl_decisions` | `id`, `project_id`, `gate_name`, `proposal`, `critic_verdict`, `status='pending'` | INSERT |
| `categorias` | `es_central`, `concern_label`, `metadatos` | UPDATE |
| `saturation_metrics` | `code_id`, `rolling_std`, `saturation_status`, `documents_since_change` | UPSERT |
| `paradigm_states` | `id`, `code_id`, `proyecto_id`, `iteration`, `did_state_expand`, `expansion_type`, `paradigm_snapshot`, `integration_memo` | INSERT |
| `category_definition_versions` | `id`, `category_id`, `project_id`, `version`, `name_at_version`, `definition_at_version`, `trigger`, `trigger_detail` | INSERT |
| `conceptual_relationships` | `id`, `project_id`, `category_ids`, `theoretical_code_id`, `researcher_question`, `elaboration_status`, `converging_doc_count`, `diverging_doc_count`, `conceptual_fit`, `layer`, `position_tension` | INSERT |
| `elaboration_memos` | `id`, `project_id`, `elaboration_type`, `relationship_id`, `content` | INSERT |
| `ecosystem_layouts` | `id`, `project_id`, `version`, `blob_positions`, `ghost_positions`, `fog_zones`, `physics_params` | INSERT |
| `theoretical_codes` | — | INSERT (seed, if not exists) |
| `proyectos` | `estado` | UPDATE (`coding→finding_cc→reducing→saturating→building_db→playground_ready`) |

#### FAST Worker

| Table | Column(s) | Operation |
|-------|-----------|-----------|
| Returns punctuated text | — | No DB writes (returns to caller) |
| `proyectos` | `population_assumption` | UPDATE (population generalizer) |

---

## Summary: Complete DB Write Map

| DB Table | Who Writes | What Fields |
|----------|-----------|-------------|
| `documentos.estado` | Orchestrator, Transitions, NLP worker, Heavy worker | State transitions: crudo→segmentando→segmentado→procesando→listo→sintetizado, error |
| `segmentos` | NLP worker (`segmentar_documento`) | id, documento_id, texto, posicion, conteo_tokens, es_anomalia, embedding, glaser_type |
| `document_processes` | Heavy worker (A2, F2.3) | id, documento_id, proceso_description, similarity, difference, prime_mover, confidence, sense_status |
| `population_contexts` | Heavy worker (A1) | id, proyecto_id, surprising_details, language_patterns, data_production_context, source_document_ids, version |
| `categorias` | Heavy worker (B2, synthesizer, selective coding) | id, proyecto_id, nombre, definicion, version, es_central, concern_label, metadatos |
| `codigos_segmento` | Heavy worker (B2.5 grounding) | id, categoria_id, segmento_id |
| `incident_groups` | Heavy worker (F2.3, B1) | Incident grouping and labeling |
| `hypotheses` | Heavy worker (A3, B3) | id, project_id, text, level, confidence, status, concern_labels |
| `memos` | Heavy worker (A3, B3, synthesis, config critic, theoretical coding) | id, proyecto_id, tipo, contenido |
| `saturation_metrics` | Heavy worker (B17, saturation loop) | code_id, rolling_std, saturation_status, documents_since_change |
| `paradigm_states` | SelectiveElaborator, saturation loop | id, code_id, proyecto_id, iteration, did_state_expand, expansion_type, paradigm_snapshot, integration_memo |
| `category_definition_versions` | ElaborationEngine, RenameDetector | id, category_id, project_id, version, name_at_version, definition_at_version, trigger, trigger_detail |
| `conceptual_relationships` | ElaborationEngine, database A/B pipelines | id, project_id, category_ids, theoretical_code_id, researcher_question, elaboration_status, converged/diverged counts, conceptual_fit, layer, tension, resolution |
| `elaboration_memos` | ElaborationEngine, GhostConnector | id, project_id, elaboration_type, relationship_id/category_id/memo_id, content |
| `ecosystem_layouts` | `_prepare_playground_for_project` | id, project_id, version, blob_positions, ghost_positions, fog_zones, physics_params |
| `theoretical_codes` | TheorySeeder | id, project_id, name, family, description, glaserian, user_defined, evaluation_logic, output_schema, compatible_with, layer, visualization_hint |
| `hitl_decisions` | hitl_gate (transitions.py) | id, project_id, gate_name, proposal, critic_verdict, status |
| `processing_states` | Transitions, Orchestrator | entity_type, entity_id, step (dedup markers) |
| `pipeline_runs` | Orchestrator | id, project_id, status, triggered_by, summary |
| `pipeline_tasks` | Transitions, Orchestrator | id, run_id, document_id, celery_task_id, task_name, queue, status, doc_estado_before |
| `proyectos` | Population generalizer, transitions | estado, population_assumption (UPDATE); language, object_of_study, pause_mode (READ) |
| `code_document_summaries` | util_map_synthesis | code_id, documento_id, summary |
| `code_global_summaries` | util_reduce_synthesis | code_id, summary |

---

> **Total unique agents identified**: ~90 (77 prompt directories + agent families + internal functions).
> **Total DB tables written to**: 20+ distinct tables across the pipeline.
> **HITL gates**: 7 named gates (pattern_of_interest, core_category, selective_reduction, core_saturation, database_a, database_b, global_saturation).
