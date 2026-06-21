# GT System: A Computational Embodiment of Classic Grounded Theory

## Conference Paper Support Report — Architecture & Theory Assessment

---

## Executive Summary

The GT system is a **distributed multi-agent pipeline** that implements Classic Grounded Theory (CGT) in the Glaserian tradition. Unlike general-purpose QDA tools (NVivo, ATLAS.ti), the system **architecturally embodies** CGT methodology: its separation of proposer/critic/HITL, its context isolation rules, its 4-signal saturation panel, and its delayed literature integration are constitutive of the system's operation, not optional features.

The system's most significant theoretical contributions are: (1) the **proposer→critic→HITL** pattern as a faithful translation of Glaser's "theoretical sensitivity" into computational architecture; (2) the generalization of "main concern" to **"pattern of interest"** with configurable `object_of_study`; (3) the **re-specification cascade** pattern that formalizes CGT's non-linear iterative refinement across five abstraction levels; and (4) the **4-signal saturation panel** that operationalizes Glaser's concept of saturation as conceptual completeness (not incident count).

The system's deepest tension — between emergence and computation — is not resolved but is thoughtfully managed through architectural humility: algorithms propose, humans decide. Every computational signal terminates in a 🛑 HITL gate.

---

## 1. System Architecture Overview

### 1.1 Infrastructure Topology

The system is deployed as a **12-container Docker composition** (`docker-compose.yml`, 312 lines):

| Service | Role | Technology |
|---------|------|-----------|
| **fastapi** | API layer (18 route modules) | FastAPI + SQLAlchemy async |
| **worker-heavy** | LLM orchestration (77 task functions, ~4400 LOC) | Celery + Together.ai |
| **worker-nlp** | NLP pipeline (segmentation, embeddings, enrichment) | Celery + spaCy + Stanza + TEI |
| **worker-fast** | Algorithmic tasks (stats, verification) | Celery |
| **postgres** | Authoritative state (46 tables) | PostgreSQL + pgvector |
| **pgbouncer** | Connection pooling | PgBouncer (transaction mode, 200 max conn) |
| **redis** | Message broker + real-time log streaming | Redis 7 (AOF) |
| **minio** | Object storage for uploaded documents | MinIO |
| **tei** | Text Embeddings Inference | ONNX-optimized `voyage-4-nano-ONNX` |
| **frontend** | React/TypeScript SPA | Node 22 + rsbuild |
| **clamav** | Document virus scanning | ClamAV |

### 1.2 Three-Tier Worker Split

The worker decomposition is a critical architectural decision (`docker-compose.yml` L169-280):

| Tier | Queue | Concurrency | Memory | Profile |
|------|-------|-------------|--------|---------|
| **worker-heavy** | `heavy` | prefork (default) | negligible | I/O-bound (LLM API calls) |
| **worker-nlp** | `nlp` | `--concurrency=1` | 6GB hard limit | CPU+memory-bound (spaCy ~600MB, Stanza ~2GB) |
| **worker-fast** | `fast` | default | unspecified | Light algorithmic tasks |

**Rationale**: CPU-heavy NLP tasks (segmentation, coreference resolution, embedding generation) are isolated from I/O-bound LLM orchestration. The NLP worker uses `concurrency=1` because spaCy and Stanza are not thread-safe. The heavy worker has no `mem_limit` because it's purely API-bound.

### 1.3 Route Architecture

The FastAPI backend exposes **117 endpoints** across 18 route modules (`backend/app/main.py` L121-138):

```
admin, analysis, auth, chain_runs, coding, config_info,
documents, elaboration, events, hitl, hypotheses, memos,
ping, pipeline, projects, rag, setup, theoretical_codes
```

However, the gap analysis (`04_gap_cross_reference.mermaid`) reveals that **55 endpoints (47%) have no frontend consumer**, including RAG search, hypothesis CRUD, individual memo CRUD, population context CRUD, and coding styles — representing significant architectural dead weight.

---

## 2. Phase-to-Code Map

### Complete Pipeline Traceability

| CGT Phase | Sub-step | Task/Function | File:Line | Tier | Pattern |
|-----------|----------|---------------|-----------|------|---------|
| **0. Configuration** | Research question builder + critic | `fc_research_question_builder` → `fc_research_question_critic` | Celery dispatch | PRO→PRO | Proposer→Critic |
| **1. Data Preparation** | Punctuation fix | `util_punctuator` | Celery dispatch | PRO | Independent |
| | Glaser type classification | `classify_document_with_validation()` | `workers/heavy/glaser_classifier.py` | PRO→FLASH validator | 3-step + validator loop |
| | Segmentation | `segmentar_documento` | `workers/nlp/tasks.py` | NLP (spaCy/Stanza) | Non-LLM |
| | Pattern + incident extraction | `extract_patterns_and_incidents()` | `workers/heavy/pattern_extractor.py` | PRO | Unified call |
| | Per-document pipeline | `process_document_agents_a()` | `workers/heavy/tasks.py:853-1036` | Mixed | Sequential + resume |
| **2. Open Coding** | Population context | `a1_build_population_context()` | `workers/heavy/tasks.py:163-272` | PRO | Accumulated memory |
| | Process identification | `a2_identify_process()` | `workers/heavy/tasks.py:280-420` | PRO | Per-document |
| | Sense making | `a3_make_sense()` | `workers/heavy/tasks.py:425-561` | PRO | Emergent (≥3 docs) |
| | Incident grouping | `b1_group_incidents()` | `workers/heavy/comparator.py:44-246` | PRO | AI-only, 1-pass |
| | Label groups | `b2_label_groups()` | `workers/heavy/labeler.py` | PRO | SelfRefinement loop |
| | Critique labels | `b3_critique_labels()` | `workers/heavy/label_critic.py` | FLASH | Standalone diff |
| | Synthesize categories | `synthesize_categories()` | `workers/heavy/synthesizer.py` | PRO | Merge new+previous |
| | Configuration critique | `critique_configuration()` | `workers/heavy/config_critic.py` | PRO | Post-batch review |
| | Pattern verification | `verify_core_pattern()` | `workers/heavy/pattern_verifier.py` | PRO | Every 3 docs |
| **3. Core Emergence** | Main concern sensing | `task_main_concern_pipeline()` | `workers/heavy/tasks.py:2653-2831` | PRO→PRO→HITL | SQL-free proposer |
| | Core category emergence | `task_core_emergence_pipeline()` | `workers/heavy/tasks.py:2892-3115` | PRO→FLASH→HITL | SQL top-3 seed |
| | Maturity gate | `_maturity_gate()` | `workers/heavy/tasks.py:1504-1530` | SQL-only | 2 conditions |
| **4. Selective Coding** | Selective reduction | `task_selective_reduction_pipeline()` | `workers/heavy/tasks.py:3122-3290` | PRO→PRO→HITL | Informed clustering |
| | Core saturation loop | `task_core_saturation_loop()` | `workers/heavy/tasks.py:3457-3807` | PRO→FLASH (per doc) | 4-signal panel gate |
| | Theoretical sampling | `task_a06_theoretical_sample()` | `workers/heavy/tasks.py:1729-1802` | SQL CTE | ANTI-JOIN stratified |
| | Paradigm integration | `fe_paradigm_integrator` | Celery dispatch | PRO | Post-loop |
| | Database A pipeline | `task_database_a_pipeline()` | `workers/heavy/tasks.py:3870-4019` | PRO→PRO→HITL | Flat nodes |
| | Database B pipeline | `task_database_b_pipeline()` | `workers/heavy/tasks.py:4023-4284` | PRO→PRO→HITL | Free-theory edges |
| | Global saturation check | `task_global_saturation_check()` | `workers/heavy/tasks.py:4288-4393` | SQL checks | 3 conditions |
| | Phase coordinator | `selective_coding_coordinator()` | `workers/heavy/tasks.py:2513-2622` | Orchestrator | Serial phases A→E |
| **5. Theoretical Coding** | Ghost blob mapping | `f6b_ghost_blob_mapper` | Celery dispatch | PRO | Orphan→category |
| | Memo theoretical tagging | `task_memo_theoretical_tagger()` | `workers/heavy/tasks.py:2634-2638` → `workers/heavy/theoretical.py:23-69` | FLASH | 12 families |
| | Conceptual elaboration | `f6b_conceptual_elaborator` | `backend/app/services/elaboration_engine` | PRO | Multi-agent |
| | Rename suggestion | `f6b_rename_suggester` | Celery dispatch | PRO | Better names |
| **6. Writing** | Natural writer | `write_section()` | `workers/heavy/writer.py:28-147` | PRO | From memo stacks |
| | Writing critic | `critique_section()` | `workers/heavy/writer.py:150-230` | PRO | SAT/MOD/FORCED |
| | Gap feeler | `feel_gaps()` | `workers/heavy/writer.py:233-297` | FLASH (background) | Non-blocking |
| **7. Literature** | Literature comparer | `compare_literature()` | `workers/heavy/literature.py:28-90` | PRO | Theory vs fragments |
| | Literature critic | `critique_literature_dialogue()` | `workers/heavy/literature.py:93-170` | PRO | Detect forcing |
| **Transversal** | ReSpec signal evaluation | `evaluate_respec_signals()` | `workers/heavy/respect_agent.py:30-182` | SQL queries | 5 signal types |
| | ReSpec lower-level query | `query_lower_level()` | `workers/heavy/respect_agent.py:185-287` | SQL CTEs | Hierarchy navigation |

---

## 3. Theoretical-Methodological Alignment

### 3.1 The Proposer→Critic→HITL Pattern: Translating "Theoretical Sensitivity"

Glaser defined theoretical sensitivity as "the ability to generate concepts from data and to relate them according to normal models of theory" (*Theoretical Sensitivity*, 1978, p. 2). The system's **proposer→critic→HITL** rhythm (`kb.md` §1, L47-53) is the architectural translation of this human quality:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PROPOSER    │ ──▶ │   CRITIC     │ ──▶ │  HITL GATE   │
│  (PRO tier)  │     │  (PRO/FLASH) │     │  (Redis→FE)  │
│  Generates    │     │  Evaluates   │     │  Researcher   │
│  candidates   │     │  against CGT │     │  decides      │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Concrete implementations** across all 7 phases (`workers/heavy/tasks.py`):

| Decision Point | Proposer | Critic | Gate | Lines |
|---------------|----------|--------|------|-------|
| Pattern of interest | `fc_main_concern_proposer` (PRO) | `fc_main_concern_critic` (PRO) | `hitl_gate("pattern_of_interest")` | 2653-2831 |
| Core category | `fc_core_category_proposer` (PRO) | `fc_core_emergence_critic` (FLASH) | `hitl_gate("core_category")` | 2892-3115 |
| Selective reduction | `fd_selective_reduction_proposer` (PRO) | `fd_selective_reduction_critic` (PRO) | `hitl_gate("selective_reduction")` | 3122+ |
| Core saturation | `fe_core_saturation_proposer` (PRO) | `fe_core_saturation_critic` (FLASH) | Per-document inline | 3670-3702 |
| Database A | `ff_database_a_proposer` (PRO) | `ff_database_a_critic` (PRO) | `hitl_gate("database_a")` | 3870+ |
| Database B | `ff_database_b_proposer` (PRO) | `ff_database_b_critic` (PRO) | `hitl_gate("database_b")` | 4023+ |
| Theoretical writing | `natural_writer` (PRO) | `writing_critic` (PRO) | User review | `writer.py:28-230` |

**Key insight**: The critic tier varies by phase — FLASH for quick interchangeability checks, PRO for deeper qualitative evaluation. This tiered approach optimizes cost while maintaining rigor.

### 3.2 Emergence vs. Forcing: Context Isolation as Architectural Principle

The refactoring document (`1-Refaccion open coding.md` §12, L935-937) diagnoses a fundamental tension: "En CGT hay una tensión fundamental entre **emergencia** (requiere aislamiento) y **síntesis** (requiere contexto)."

The corrected design enforces **strict context isolation** through controlled information flow:

| Agent | Sees | Does NOT see | Rationale |
|-------|------|-------------|-----------|
| A1 (incident_extractor) | Current segment only | Existing categories | Prevents confirmation bias |
| A2 (pattern_extractor) | Current document only | Cross-document patterns | Patterns emerge within, not across |
| B1 (incident_comparator) | Raw incidents only | Existing categories | "Si ve categorías existentes, fuerza el incidente nuevo a encajar en moldes viejos" (`1-Refaccion.md` L944) |
| B2 (pattern_labeler) | Raw incident groups | Labels from other groups | Independent labeling |

This is the system's **strongest methodological commitment**. The incident comparator (`workers/heavy/comparator.py:44-246`) was radically redesigned: the old version used cosine pre-filtering + pairwise LLM comparison + Union-Find (three error-accumulating steps). The new version (`b1_group_incidents`) sends ALL incidents in a single PRO call with document provenance tags — no pre-filter, no pairwise comparison, no Union-Find. The AI does all grouping.

### 3.3 "Main Concern" → "Pattern of Interest": Theoretical Justification

The terminology shift from Glaser's "main concern" to the system's "pattern of interest" (`kb.md` §3, L87-107) is a **theoretically sophisticated evolution**. The refactoring document §10.2 (L701-709) provides a systematic mapping:

```python
object_of_study ∈ {concern, emotion, behavior, discourse, identity}
```

Each corresponds to a different "lente" through which the same CGT method operates. This is consistent with Glaser's later work (*The Grounded Theory Perspective III*, 2005), where he acknowledged grounded theory could be applied beyond the "basic social process" framework.

The coding style adapts accordingly (`workers/heavy/tasks.py:56-71`):
- `concern` → gerund codes, "layman" role, Glaser's 4 questions
- `emotion` → nominal emotion codes, "emotional pattern researcher"
- `behavior` → verb codes, "behavioral pattern researcher"
- `discourse` → nominal discourse codes, "discourse analyst"
- `identity` → nominal identity codes, "identity researcher"

**Risk**: The "layman" role for `concern` assumes an LLM can simulate theoretical naïveté, but the model's training data contains extensive social science frameworks. This simplification masks the model's inherent biases.

### 3.4 Literature Treatment: Near-Perfect Fidelity

The system's implementation of Glaser's literature policy (`kb.md` §12, L489-527) is **exemplary**:

- **Timing**: Literature integration occurs **only in Phase 5** (the final phase), after natural writing is complete. The `task_literature_comparer` (`workers/heavy/literature.py:28-90`) receives the "complete theory draft" as input.
- **Framing**: Literature is treated as **data, not authority** — `compare_literature()` codes literature fragments as incidents and evaluates them against the complete theory (EXTENDS, MODIFIES, INTEGRATES, TRANSCENDS).
- **Critic**: `critique_literature_dialogue()` (`workers/heavy/literature.py:93-170`) specifically detects forcing, authority bias, and name-dropping.
- **Integration style**: According to `kb.md` §12.3 (L521): "La integración erudita va en **notas al pie** — no interrumpas la voz de tu teoría para debatir con autoridades."

### 3.5 Saturation: The 4-Signal Panel

Glaser's definition of saturation is deceptively simple: "Saturation is reached when no new properties of the category emerge" (*Theoretical Sensitivity*, 1978, p. 64). The system operationalizes this through four signals (`workers/heavy/tasks.py:3301-3446`, `kb.md` §6.4, L244-253):

| Signal | Source Table | Computation | Threshold | Fidelity Assessment |
|--------|-------------|-------------|-----------|-------------------|
| **1. Mathematical** | `saturation_metrics` | `rolling_std` of embeddings | `≤ 0.3` | ⚠️ Weakest — embedding similarity ≠ conceptual interchangeability |
| **2. Qualitative** | `paradigm_states` | Sliding window of 5 `did_state_expand` | All 5 = False | ✅ Strong — maps to "no new properties" |
| **3. Coverage** | `paradigm_states.paradigm_snapshot` (JSONB) | Count properties across dimensions | ≥ 80% of target | ✅ Strong — dimensional completeness |
| **4. Integration** | `conceptual_relationships` | `COUNT(*)` of relationships | ≥ 1 relationship | ✅ Innovative — relational saturation |

**Key design decision** (`tasks.py:3556-3598`): LLM is ONLY invoked when all 4 signals suggest stability (`_check_all_signals_stable()`). If any signal says "unstable", the system skips the expensive LLM call entirely — the cheap SQL/algorithmic signals act as a cost-saving pre-filter.

**Theoretical concern**: Embedding-based pre-filtering (signal #1) introduces conceptual risk. Two theoretically distinct categories can have high embedding similarity; two theoretically identical incidents can have different embeddings due to vocabulary. The system mitigates this by routing through qualitative verification, but any computational pre-filter introduces potential for premature conceptual closure.

---

## 4. Architectural Patterns & Innovations

### 4.1 Pattern: Proposer→Critic→HITL as Universal Rhythm

This pattern is applied **consistently across 7+ decision points** with tier differentiation. Three specialized patterns emerge:

- **PRO→PRO→HITL**: For high-stakes decisions (main concern, selective reduction, writing)
- **PRO→FLASH→HITL**: For routine checks (interchangeability, core saturation per-doc)
- **FLASH non-blocking**: For background scanning (gap feeling, `feel_gaps()` in `writer.py:233-297`)

### 4.2 Pattern: Checkpoint-Based Abort/Resume

The `AbortableTask` base class (`workers/heavy/tasks.py:793-837`) with SIGTERM handling and `checkpoint_helpers` module enables abort/resume on long-running per-document pipelines. The `process_document_agents_a()` function (`tasks.py:853-1036`) checks `self._aborted` at every step boundary and uses checkpoint step status (`in_progress`/`completed`) to resume from the first uncompleted step.

### 4.3 Pattern: SQL/Algorithmic Pre-Filter → LLM → HITL Gate

Cost optimization through pre-filtering:
1. **SQL** checks cheap conditions (document count, maturity gate)
2. **Algorithmic** checks compute metrics (embedding variance, coverage)
3. **LLM** invoked only when pre-filters pass
4. **HITL** gate confirms the decision

Examples: saturation panel (`_compute_saturation_panel → fe_core_saturation_proposer → HITL`), maturity gate (`_maturity_gate → task_core_emergence_pipeline → HITL`).

### 4.4 Pattern: Ghost Blob Absorption

**Ghosts** are memos that don't link to any existing category (`04_gap_cross_reference.mermaid` D11: `ghosts` table, 5 columns). The Ghost Blob Mapper agent (`f6b_ghost_blob_mapper`, PRO) proposes category assignments for orphan memos. Ghosts appear in the Playground's `EcosystemCanvas` as disconnected blobs that the researcher can drag to connect.

The ReSpec system (`workers/heavy/respect_agent.py:113-134`) monitors orphans: if `COUNT(memos without elaboration_memos link) > 5`, it fires a re-specification suggestion.

### 4.5 Pattern: ReSpec (Re-Specification) Cascade

The re-specification system (`1-Refaccion open coding.md` §20, L1627-2036; `workers/heavy/respect_agent.py`) is one of the system's **most innovative theoretical contributions**. It formalizes CGT's non-linear iterative refinement across 5 abstraction levels:

```
Raw Data → Incidents → Categories → Core Category → Theory
     ↓           ↓           ↓             ↓            ↓
  ReSpecTool  ReSpecTool  ReSpecTool    ReSpecTool   ReSpecTool
  query_lower  query_lower  query_lower   query_lower  query_lower
```

**5 signal types monitored** (`respect_agent.py:30-182`):
| Signal | Query | Threshold | Severity |
|--------|-------|-----------|----------|
| Ambiguous incidents | `extracted_incidents` confidence < 0.5 | >10 | warning |
| Rejected labels | `incident_groups.status = 'rejected'` | >3 | warning/critical |
| Unresolved divergence | `conceptual_relationships.elaboration_status = 'tense'` without resolution | >2 | warning |
| Orphan memos | `memos` without `elaboration_memos` link | >5 | info |
| Empty axes | `paradigm_states` without any `did_state_expand = true` | >0 | warning/info |

The **Stage-Gate Review** (`1-Refaccion.md` L1832-2036) places a glowing purple button at the end of each phase, signaling that review opportunities exist, but never *forcing* review. This preserves the researcher's autonomy while providing computational vigilance.

### 4.6 Pattern: Theoretical Playground

The Playground (`kb.md` §8, L364-416) creates a **hybrid ecosystem** that preserves the spirit of Glaser's physical memo sorting while adding computational capabilities:

| Physical Sorting (Glaser) | Theoretical Playground (GT System) |
|---------------------------|-----------------------------------|
| Physical memo cards on a table | Organic blobs (categories) on a canvas |
| Manual grouping by theme | Drag-and-drop arrangement |
| Serendipitous juxtapositions | Ghost absorption, tendrils, golden fissures |
| Single sorting session | Sorting Log: multiple sessions recorded |
| Human pattern recognition | `memo_theoretical_tagger` (FLASH) pre-classifies by family |
| Implicit structure | Cross-family synthesizer detects robust groups |

The **12 Glaserian theoretical coding families** are seeded at startup (`backend/app/main.py` L92, `backend/app/services/theory_seeder.py`) and their evaluation logic is inspectable and adjustable.

---

## 5. LLM Orchestration

### 5.1 Tier Differentiation: PRO vs FLASH

Model configuration (`workers/heavy/llm_client.py:127-147`):

```python
_MODEL_FLASH = "nvidia/nemotron-3-ultra-550b-a55b"    # configurable
_MODEL_PRO   = "deepseek-ai/DeepSeek-V4-Pro"           # configurable

_TIER_MAX_TOKENS = {"FLASH": 4096, "PRO": 8192}
_TIER_TEMPERATURE = {"FLASH": 0.1, "PRO": 0.3}
```

The tier is declared in each prompt's YAML frontmatter. `run_agent()` tries PRO first, then FLASH as fallback.

**Cost optimization distribution**:
- **FLASH** (Nemotron 550B): label critique, gap feeling, memo theoretical tagging, evidence classification, core emergence critic (interchangeability), saturation critic
- **PRO** (DeepSeek V4 Pro): all proposers, main concern detection, writing, literature comparison, selective reduction

### 5.2 Chain of Thought Strategy

The refactoring document (`1-Refaccion.md` §14, L1126-1222) diagnoses a critical issue: `response_format=json_object` at `llm_client.py:880` suppresses reasoning tokens. The system captures `reasoning_content` at `llm_client.py:896-898` but it doesn't flow into `_self_evaluation` parsing.

**Resolution**: Each agent prompt internally structures its reasoning. For example, the main concern proposer prompt structures a three-sequential-question CoT within the JSON output. The `_self_evaluation` mechanism (`llm_client.py:780-807`) provides a structured retry signal: `needs_retry`, `retry_reason`, `suggested_action` (proceed/retry/escalate_to_hitl/skip/abort).

### 5.3 Prompt Management

Prompts live in `backend/app/prompts/agents/{agent_id}/` as:
- `prompt.md` — YAML frontmatter (agent id, tier, constraints, input_state) + System/User sections
- `schema.{lang}.json` — i18n output schemas (es, en, de, pt)

~80 agent prompts organized in families: `fa_*` (Phase A), `fb_*` (Phase B), `fc_*` (Phase C), `fd_*` (Phase D), `fe_*` (Phase E), `ff_*` (Phase F), `f6a-f6d` (writing/literature/applicability).

### 5.4 RAG Strategy

**RAG is deliberately absent from the core CGT pipeline**. The `GET /rag/search` and `GET /rag/context/{code_id}` endpoints exist in the API but are explicitly **not consumed** by the frontend (`04_gap_cross_reference.mermaid` G8, U12). This enforces the CGT principle that the analyst works directly with emergent data, not retrieving similar segments.

**Where embeddings ARE used**:
- `categorias.embedding_centroide` (pgvector) for similarity-based Playground recommendations
- `RenameDetector` service uses TEI embeddings to detect semantic overlap in category names

---

## 6. Data Traceability

### 6.1 Schema Architecture

The **46-table PostgreSQL schema** supports the full CGT traceability chain:

```
DOCUMENTO (id)
  └── SEGMENTO (documento_id FK)
        ├── INCIDENTE (segmento_id FK) → INCIDENT_GROUP (via incident_ids_json)
        ├── CODIGO_SEGMENTO (segmento_id FK, categoria_id FK)
        │     └── CATEGORIA (categoria_id FK)
        │           ├── DEFINITION_VERSION (categoria_id FK)
        │           ├── RENAME_SUGGESTION (categoria_id FK)
        │           ├── RELATIONSHIP (category_a_id/category_b_id FK)
        │           ├── DOC_CODE (categoria_id FK, documento_id FK)
        │           └── PARADIGM_STATES (code_id FK)
        │
        └── AGENT_OUTPUT (documento_id FK, nullable)

PROYECTO (id)
  ├── CONCERN (proyecto_id FK)
  ├── POPULATION_CONTEXT (proyecto_id FK) — versioned
  ├── HYPOTHESIS (proyecto_id FK)
  ├── HITL_DECISION (proyecto_id FK) — gate_name distinguishes phases
  ├── THEORETICAL_CODE (proyecto_id FK)
  └── MEMO (proyecto_id FK) — user or agent-created
```

### 6.2 Database A vs Database B

**Database A** (`task_database_a_pipeline`, `tasks.py:3870-4019`): Flat nodes with `entity_type` (core_category, related_category, secondary). Each node contains: `label`, `entity_type`, `definition` (integrated from paradigm_state), `properties[]`, `is_core`, `grounding_incidents[]`. Stored in `database_nodes` table.

**Database B** (`task_database_b_pipeline`, `tasks.py:4023-4284`): Edges between nodes with **free-theory `relationship_type`** — not predefined types. Each edge cites evidence from hypotheses. Stored in `database_edges` table.

This separation enforces the Glaserian distinction between conceptual elements (Database A) and their interconnections (Database B).

### 6.3 Memo System

The refactoring document (`1-Refaccion.md` §17, L1424-1563) redesigned the memo system with:
- **Versioned memos** (`memo_versions` table, `source` field: system/user_modified/user_created)
- **Structured fields**: `linked_category_ids`, `linked_incident_ids`, `evidence_quotes`
- **@ MentionSearch** with hierarchical color-coding (purple=categories, green=incidents, yellow=quotes)
- **Living document flow**: agent generates → researcher edits → version preserved

---

## 7. Gaps, Technical Debt, and Risks

### 7.1 Critical Backend-Frontend Gaps

From `04_gap_cross_reference.mermaid`:

| Gap | Severity | Description |
|-----|----------|-------------|
| **GAP-1** | CRITICAL | Category fields (nombre, definicion, es_central) fetched but only `cats.length` displayed — 83% waste |
| **GAP-2** | HIGH | `DocPipelineLog.steps` (6 booleans) never read — 75% waste |
| **GAP-3** | HIGH | `EcosystemLayout` persistence: positions saved to DB but frontend recalculates, `saveEcosystemLayout()` never called |
| **GAP-4** | HIGH | `TheoreticalCode[]` fetched by PlaygroundContext but **zero components read it** — 100% dead data round-trip |
| **GAP-5** | MEDIUM | Segment detail fields (parafrasis, posicion, conteo_tokens, es_anomalia) never rendered — 71% waste |
| **GAP-6** | MEDIUM | Saturation gaps + theoretical model endpoints exist but frontend never calls them |
| **GAP-8** | LOW | 55/117 endpoints (47%) have no frontend consumer |

### 7.2 Hardcoded Parameters

From `workers/heavy/tasks.py` and `workers/heavy/respect_agent.py`:

| Parameter | Location | Value | Should Be |
|-----------|----------|-------|-----------|
| `AMBIGUOUS_INCIDENT_THRESHOLD` | `respect_agent.py:24` | 10 | Configurable |
| `REJECTED_LABEL_THRESHOLD` | `respect_agent.py:25` | 3 | Configurable |
| Rolling std threshold | `tasks.py:3341` | `≤ 0.3` | Configurable |
| Coverage threshold | `tasks.py:3444` | `≥ 0.8` | Configurable |
| Qualitative stability window | `tasks.py:3374` | 3 consecutive | Configurable |
| TheoSampler trigger | `tasks.py:3566` | 3 consecutive_no_expand | Configurable |
| Glaser classifier max rounds | `tasks.py:2862` | 3 | Configurable |
| Segment limit in prompts | `tasks.py:194,317,3663` | 15/8/5000 chars | Configurable |

### 7.3 Theoretical Risks

1. **The auto-advance mode** (`pause_mode = auto`, `secuencia_cgt.mermaid` L203-206): Auto-selects top candidates without researcher review. This contradicts CGT's core principle of human theoretical judgment. The kb.md labels outputs as "provisional" but the feature remains a significant departure from Glaserian CGT.

2. **Core emergence is partially algorithmic**: The SQL top-3 pre-filter (`tasks.py:2918-2934`) selects categories by graph-theoretic centrality. Truly latent patterns with fewer hypothesis connections may never reach the LLM evaluator. This contradicts the process diagram's "No scoring, no algorithms" rhetoric (Phase 2).

3. **The 3-document batch boundary**: Both the refactoring document and kb.md use batches of 3 as the trigger for synthesis events. Glaser never specified a batch size. This hard threshold could force premature synthesis or delay necessary synthesis.

4. **The `score ≥ 4` threshold** (`kb.md` §6.3, L225): Categories must appear in ≥4 documents to enter the saturation loop. Glaser explicitly stated "frequency is not a criterion for theoretical relevance" (*Theoretical Sensitivity*, 1978, p. 70). A category appearing in only 2 documents might be theoretically crucial.

5. **Embedding-based pre-filtering**: The mathematical saturation signal and RAG-based evidence retrieval rely on semantic embeddings that measure similarity, not conceptual interchangeability. The system mitigates this through qualitative verification but the risk of premature conceptual closure through algorithmic pre-filtering is real.

6. **Deskilling**: The system performs enormous intellectual work (classifying data types, extracting incidents, grouping by interchangeability, proposing labels, generating hypotheses, detecting gaps). A novice researcher might never develop the skills to do these tasks manually — a particular concern given CGT's insistence that the researcher *must* do the work to develop theoretical sensitivity.

---

## 8. Comparative Assessment

### 8.1 Comparison with Existing Tools

| Dimension | General QDA Tools (NVivo, ATLAS.ti) | GT System |
|-----------|-------------------------------------|-----------|
| **Methodology** | Agnostic — supports any method | Embody CGT in architecture |
| **Coding** | Manual with optional auto-coding | Multi-agent with proposer→critic |
| **Saturation** | Researcher judges intuitively | 4-signal computational panel |
| **Sorting** | Manual code trees | Interactive Playground canvas |
| **Literature** | Integrated ad hoc | Delayed to Phase 5 by design |
| **HITL gates** | None | 15+ gates across all phases |
| **Traceability** | Code-to-segment links | Incident→code→category→theory chains |
| **Infrastructure** | Desktop application | Distributed Docker microservices |
| **Learning curve** | Low | High (38 agents, 65-item checklist) |

### 8.2 Unique Contributions

1. **Architectural embodiment of methodology**: The system's architecture *is* a theory of CGT. The proposer→critic→HITL pattern, context isolation rules, and cascade propagation model are methodological claims expressed as software architecture.

2. **Computational constant comparison**: The B1→B2→B3 flow implements Glaser's constant comparative method as a computational pipeline with strict separation of concerns — not automating comparison, but structuring it to prevent confirmation bias.

3. **Saturation as multi-signal construct**: The 4-signal panel makes visible what human researchers typically judge intuitively.

4. **Theoretical coding as interactive canvas**: The Theoretical Playground creates a computational analog of physical memo sorting while adding cross-family comparison and automatic suggestion of connections.

5. **Modal architecture**: Support for multiple `object_of_study` types demonstrates CGT's flexibility beyond Glaser's canonical "main concern."

---

## 9. Recommendations for the Conference Paper

### 9.1 Strengths to Emphasize

1. **The proposer→critic→HITL pattern** as a faithful computational translation of Glaser's theoretical sensitivity — delegate pattern recognition to LLMs, reserve theoretical judgment for humans.

2. **The re-specification cascade** as a genuinely novel contribution to CGT methodology — formalizes iterative refinement without imposing algorithmic determinism.

3. **The 4-signal saturation panel** as an operationalization that enriches Glaser's concept with dimensional completeness and relational saturation, beyond the canonical "no new properties."

4. **Context isolation as architectural principle** — the system's most sophisticated methodological commitment, explicitly designed to prevent confirmation bias.

5. **Literature as dialogue, not authority** — the system's implementation of Glaser's most distinctive methodological prescription is exemplary.

### 9.2 Tensions to Acknowledge

1. **Emergence vs. computation**: The system uses algorithms (embedding variance, graph centrality) to pre-filter candidates, creating an unresolved tension with its rhetoric of "no scoring, no algorithms." This is honestly managed but not resolved.

2. **The auto mode**: Allowing the system to advance without human decisions contradicts CGT's core principle. This should be acknowledged as a pragmatic compromise, not a methodological feature.

3. **The "layman" role for LLMs**: Presenting an LLM as theoretically naïve is a simplification that masks training data biases.

4. **Deskilling risk**: Over-reliance on computational support could prevent researchers from developing their own theoretical sensitivity.

### 9.3 Key References for the Paper

| Reference | Description | File |
|-----------|-------------|------|
| Proposer→Critic→HITL pattern | Universal rhythm governing all phases | `kb.md` §1 L47-53; `workers/heavy/tasks.py` L2653-2831 |
| Context isolation rules | Prevents confirmation bias in open coding | `1-Refaccion open coding.md` §12 L935-991 |
| 4-signal saturation panel | Multi-dimensional saturation detection | `workers/heavy/tasks.py:3301-3446`; `kb.md` §6.4 L244-253 |
| ReSpec cascade | Hierarchical fallback across 5 abstraction levels | `1-Refaccion open coding.md` §20 L1627-2036; `workers/heavy/respect_agent.py` |
| Literature dialogue | Literature as data, not authority | `kb.md` §12 L489-527; `workers/heavy/literature.py` |
| Pattern of interest generalization | Beyond Glaser's "main concern" | `kb.md` §3 L87-107; `1-Refaccion open coding.md` §10.2 L701-709 |
| Ghost blob absorption | Orphan memo→category mapping | `workers/heavy/theoretical.py`; `04_gap_cross_reference.mermaid` D11 |
| 3-tier worker split | CPU/NLP/LLM isolation | `docker-compose.yml` L169-280 |
| Theoretical Playground | Hybrid sorting: physical + computational | `kb.md` §8 L364-416 |
| Maturity gate | SQL-only precondition before core emergence | `workers/heavy/tasks.py:1504-1530` |
| Incident grouper redesign | 1-pass AI-only grouping | `workers/heavy/comparator.py:44-246` |
| AbortableTask + checkpoint | Resume support on long pipelines | `workers/heavy/tasks.py:793-837, 853-1036` |
| Prompt library with i18n | File-based agent prompt system | `backend/app/prompts/agents/{agent_id}/` |
| Frontend-backend gap analysis | 47% dead endpoints, data waste | `04_gap_cross_reference.mermaid` |

---

*Report compiled from: `kb.md` (759 lines), `proceso-cgt.puml` (5 phases), `secuencia_cgt.mermaid`, `1-Refaccion open coding.md` (2037 lines), `04_gap_cross_reference.mermaid`, `docker-compose.yml` (312 lines), `workers/heavy/tasks.py` (~4400 lines, 77 functions), plus all agent modules in `workers/heavy/`, `workers/nlp/`, `workers/fast/`, and the FastAPI backend (`backend/app/`).*
