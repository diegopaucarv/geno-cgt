## 4. Implementation

### 4.1 Methodological Foundations

Classic grounded theory (CGT) carries an ambiguity of origin. The formula that the method "studies how a population resolves its main concern" does not appear in Glaser and Strauss (1967). It consolidated later and encloses the method in a corset Glaser himself did not consistently maintain. Across decades his position was broader: grounded theory is a general method applicable to any data (Glaser, 2010); the main concern must emerge, not be preconceived (personal communication, 2016); and the core operation is constant comparison toward latent pattern discovery (Glaser, 1995).

The system adopts this broader formulation. The researcher describes the population and selects a pattern type — concern, emotion, behavior, discourse, or identity. From these two decisions, the system constructs the operational question. The defaults are intentional: how a population processes its central concern. But they are modifiable. This formulation draws on Booth et al. (2016), who define a research question as the sum of a population, a category within that population, and a question type, and on Abbott (2016), whose work on digital literacy informs how computational systems should handle qualitative inquiry.

The system also incorporates Glaser's five data types (1995) as a mandatory preprocessing layer. An agent classifies every segment as baseline (spontaneous participant experience), properline (what the participant believes they ought to say), interpreted (opinion forced by the interviewer's question), vague (evasion that may signal taboo topics), or conceptual (metaphors and jargon that encode more than they appear to). Only baseline data advances to coding; the rest is archived as context. This is a methodological decision that prevents the resulting theory from describing social norms as if they were behavior.

### 4.2 Development Trajectory

The system began as an N8N prototype — a deliberate experiment to discover which parts of CGT were hardest to automate. Two bottlenecks emerged immediately.

First, iterative incident extraction was slow, expensive, and inconsistent. Processing each segment with a separate LLM call produced different labels for the same phenomenon depending on where it appeared in the transcript. A participant seeking validation in one segment became a participant needing approval in the next — noise that corroded the constant comparison that follows extraction. The solution was to unify extraction and individual pattern detection into a single PRO call per document. One model sees the entire interview, identifies all incidents, and detects the pattern that connects them, in one pass.

Second, constant comparison scaled quadratically. One hundred incidents require 4,950 pairwise comparisons; five hundred require over 124,000. A naive pairwise approach was computationally and economically inviable. The solution was to replace pairwise comparison with single-pass conceptual grouping: all incidents go to the model together, with no pre-filter and no clustering algorithm. The model groups them in one pass, perceiving patterns across documents in ways pairwise comparison could not.

These two discoveries — unify extraction, group in one pass — defined the production architecture that followed.

### 4.3 Technical Architecture

The production system runs on four computational profiles, isolated to prevent CPU-intensive NLP tasks from blocking I/O-bound LLM calls:

| Container | Profile | Concurrency | Rationale |
|-----------|---------|-------------|-----------|
| worker-heavy | I/O-bound (LLM APIs) | Prefork | No memory limits; API calls only |
| worker-nlp | CPU+RAM-bound | 1 | spaCy (~600 MB) + Stanza (~2 GB); not thread-safe |
| worker-fast | Algorithmic | Default | Statistics, SQL checks, lightweight verifications |
| tei | Embeddings inference | N/A (HTTP) | Isolated GPU/CPU memory for voyage-4-nano-ONNX |

Two model tiers serve distinct roles. PRO (DeepSeek V4 Pro, 8192 tokens, temperature 0.3) handles generation — extracting incidents, proposing categories, drafting theory sections. FLASH (Nemotron 550B, 4096 tokens, temperature 0.1) handles verification — critiquing labels, checking saturation conditions, detecting unsupported claims. The temperature difference reflects task profiles: generation needs enough openness to perceive non-obvious patterns; verification needs consistency across repeated checks. The economic rationale is equally structural: PRO costs approximately ten times more per token than FLASH. The tier system is cost optimization in service of methodological viability — running the expensive model on every per-document check would make the system economically unusable for sustained research.

State management pairs PostgreSQL with pgvector — 46 tables with foreign-key provenance chains that allow every theoretical proposition to trace back to its source quote — with Redis for Celery message brokering and real-time log streaming to the frontend via pub/sub. Agent orchestration uses LangGraph state graphs, enabling reasoning loops, human-in-the-loop interruption handling, and conditional transitions based on project state. The React frontend communicates with the FastAPI backend via REST; pipeline progress streams through Redis pub/sub so the researcher watches the system work without refreshing.

### 4.4 Researcher Journey

From account creation to finished theory, the researcher moves through six stages.

**Setup.** The researcher creates a project and answers three questions: what population to study, what pattern type to look for, and whether to enable optional assistance. That is all. No theoretical framework. No hypotheses. The system verifies that NLP models are downloaded; on a first run, it displays a progress bar while spaCy and Stanza models download. This happens once.

**Upload and silent processing.** Transcripts are uploaded singly or in batch. Each document passes through virus scanning (ClamAV), Glaser data-type classification, NLP segmentation via a moving window of coreferences (Stanza), and unified extraction — incident extraction and individual pattern detection in a single PRO call. The system works in silence. Glaser insisted the researcher should not interfere during open coding; the system enforces this. The researcher watches progress but does not intervene.

**Batch pauses.** Every three documents, the system stops. Four panels appear: unified categories, accumulated hypotheses, candidate patterns of interest, and a configuration review. The researcher inspects each — merging categories, rejecting weak hypotheses, confirming or redirecting the emerging pattern. When the researcher modifies something, the cascade recalculates only what depends on that change. The system resumes with the next batch. The cycle repeats until all documents are processed.

**Selective coding.** When sufficient mass exists — a maturity gate requiring at least three saturated categories and two documented hypotheses — the pipeline advances automatically. The system proposes a central concern, a core category, and a reduced category system. Each proposal arrives with a critique: the system flags what the proposal may be missing, what alternative the evidence could support, and what the researcher should verify before confirming. The researcher confirms or modifies at each gate.

**Playground and writing.** Saturated categories become blobs on an interactive canvas. Relationships become connecting tendrils. Orphan memos become ghosts — draggable entities the researcher can absorb into categories. The researcher arranges the theoretical structure visually, testing family configurations and dragging concepts into place. From memo stacks, the system drafts theory sections. The researcher edits directly on the marked text. A background gap feeler continuously detects claims that lack evidential support, flagging thin zones in the emerging theory.

**Literature and closure.** Only at the end does the system integrate the literature. It treats each paper as a new interview — extracts incidents, codes them against the emergent theory, and evaluates whether the literature extends, modifies, integrates, or transcends the findings. Citations appear as footnotes, preserving the theory's own voice. The researcher reviews the dialogue table, and if everything closes, presses "Complete study." The system delivers a theory where every proposition traces down to its source quote.

### 4.5 Agent Chains

The system's 96 agents organize into eight chains, each following the proposer→critic→HITL rhythm with phase-specific variations:

| Chain | Phase | Key Agents | Tier Pattern |
|-------|-------|-----------|--------------|
| A | Data Preparation | Glaser classifier → NLP segmenter → Unified extractor → Population context | PRO → NLP → PRO → PRO |
| B | Cross-Document Synthesis | Incident grouper → Labeler ↔ Critic → Code generator → Hypothesis generator → Unification → 🛑 HITL | PRO → PRO↔FLASH → PRO → PRO → PRO |
| C | Core Emergence | Main concern proposer → Main concern critic → 🛑 HITL → Maturity gate → Core category proposer → Core emergence critic → 🛑 HITL | PRO → PRO → SQL → PRO → FLASH |
| D | Selective Reduction | Reduction proposer → Reduction critic → 🛑 HITL | PRO → PRO |
| E | Saturation (loop) | Saturation proposer → Saturation critic → Paradigm integrator → Memo generator → 🛑 HITL → [if unsaturated] Property sampler | PRO → FLASH → PRO → PRO → PRO |
| F | Database A/B | Database A proposer → Database A critic → 🛑 HITL → Database B proposer → Database B critic → 🛑 HITL → Global check | PRO → PRO → PRO → PRO |
| G | Playground & Writing | Ghost mapper → Memo tagger → Conceptual elaborator → Natural writer → Writing critic → Gap feeler → 🛑 HITL per section | PRO → FLASH → PRO → PRO → PRO → FLASH |
| H | Literature & Applicability | Literature comparer → Literature critic → 🛑 HITL → Applicability engine → Applicability critic → 🛑 HITL | PRO → PRO → PRO → PRO |

Chain A prepares each document in silence — classifying segments, extracting incidents, detecting the participant's individual pattern — before any cross-document work begins. Chain B groups all incidents from a batch in a single pass, generates codes and hypotheses, and presents the unified results for researcher review. Chain C senses the latent central concern and proposes a core category, with the researcher confirming each gate. Chain D reduces the category system to what matters for the core category, subject to researcher approval. Chain E iterates over each relevant category, expanding properties until saturation and generating memos along the way. Chain F constructs the formal node-and-edge structure of the theory — first nodes, then relations — with global closure checks. Chain G maps orphan memos onto categories, tags memos by theoretical family, drafts theory sections, and runs a background gap feeler that flags unsupported claims on every paragraph. Chain H integrates the literature at the end, treating papers as data and evaluating emergent fit.

The tier assignments follow a consistent principle: FLASH evaluates, PRO generates. The saturation critic uses FLASH because it checks a simple condition — did the paradigm state genuinely expand? The main concern critic uses PRO because it must distinguish between latent participant experience and surface discourse. This is cost optimization in service of methodological rigor.
