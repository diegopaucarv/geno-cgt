# Prerequisite Change 9 — Update pipelineChains.ts with ChainDef

**Status:** ✅ COMPLETED
**Date:** 2026-06-21
**File modified:** `frontend/src/config/pipelineChains.ts`

---

## Step 1: Read & Diagnose

### Current structure (before change)

| Element | Lines | Description |
|---------|-------|-------------|
| `AgentDef` | L17-26 | `id`, `label`, `tier`, `dependencies`, `chain?`, `chainOrder?`, `independent?`, `iterationKey?` |
| `StageDef` | L28-39 | `key`, `icon`, `label`, `agents: AgentDef[]`, `hasHITL?`, `batchTrigger?`, `minDocs?` |
| `FAMILY_COLORS` | L41-45 | Tier → hex color mapping |
| `PIPELINE_STAGES` | L47-416 | 5 stages with nested `agents` arrays |
| `canRunAgent()` | L420-430 | Checks if all deps completed |
| `areAllAgentsDone()` | L432-440 | Checks if all agents in a stage are done |

### Current `agents` by stage

| Stage | Agent count | Organization |
|-------|------------|-------------|
| data_management | 4 | All `independent: true`, sequential via `dependencies` |
| open_coding | 11 | Mix of chained (`chain` + `chainOrder`) and independent |
| selective_coding | 10 | All chained (`chain` + `chainOrder`) in 5 pairs |
| theoretical_coding | 6 | All `independent: true`, parallel via shared dep |
| writing | 3 | Chained (`chain: "Writer→Critic→Gap"`) |

---

## Step 2: Spillover Analysis

### Files importing from `pipelineChains.ts`

| File | Imports | Uses `stage.agents`? | Uses `stage.chains`? | Break risk |
|------|---------|---------------------|---------------------|------------|
| `PipelineAgents.tsx` | `StageDef`, `AgentDef`, `FAMILY_COLORS`, `canRunAgent` | Yes (L90, L100) | No | **None** — optional field |
| `Project.tsx` | `PIPELINE_STAGES`, `FAMILY_COLORS` | No (uses only `.key`, `.icon`, `.label`) | No | **None** |
| `MemoHistory.tsx` | Own private `FAMILY_COLORS` | No | No | **None** |

**Conclusion:** Adding an optional `chains?: ChainDef[]` to `StageDef` is fully backward-compatible. TypeScript interfaces with optional fields do not break existing consumers.

---

## Step 3: Pseudocode Mockups

### OLD `StageDef`
```typescript
export interface StageDef {
  key: string;
  icon: string;
  label: string;
  agents: AgentDef[];
  hasHITL?: boolean;
  batchTrigger?: boolean;
  minDocs?: number;
}
```

### NEW `StageDef` + `ChainDef`
```typescript
export interface ChainDef {
  id: string;                       // Canonical chain ID
  label: string;                    // i18n key
  agents: AgentDef[];               // In execution order
  parallel?: boolean;               // Runs alongside other chains
  sync_agent_id?: string;           // Sync point for parallel chains
  default_max_retries?: number;
  default_timeout_seconds?: number;
}

export interface StageDef {
  key: string;
  icon: string;
  label: string;
  agents: AgentDef[];               // KEPT for backward compat
  chains?: ChainDef[];              // NEW: additive layer
  hasHITL?: boolean;
  batchTrigger?: boolean;
  minDocs?: number;
}
```

---

## Step 4: Pre-Evaluation

### Does TypeScript compilation pass?
✅ Yes — 0 diagnostics errors/warnings.

### Does `PipelineAgents.tsx` still render correctly?
✅ Yes — it iterates `stage.agents` on L100 (unchanged) and groups by `agent.chain` property.

### Does `Project.tsx` still work?
✅ Yes — it iterates `PIPELINE_STAGES` using only `stage.key`/`stage.icon`/`stage.label`.

### Are chain IDs consistent with backend design?
See chain ID summary table below.

### Do we need i18n keys?
Yes — all chain labels use the `pipeline.chain.*` i18n namespace. Keys needed:

| Chain ID | i18n key |
|----------|----------|
| `data_management_main` | `pipeline.chain.data_management` |
| `open_coding_main` | `pipeline.chain.open_coding_main` |
| `open_coding_hypotheses` | `pipeline.chain.open_coding_hypotheses` |
| `selective_main_concern` | `pipeline.chain.selective_main_concern` |
| `selective_core_emergence` | `pipeline.chain.selective_core_emergence` |
| `selective_reduction` | `pipeline.chain.selective_reduction` |
| `selective_saturation` | `pipeline.chain.selective_saturation` |
| `selective_database_a` | `pipeline.chain.selective_database_a` |
| `selective_database_b` | `pipeline.chain.selective_database_b` |
| `theoretical_coding` | `pipeline.chain.theoretical_coding` |
| `writing_main` | `pipeline.chain.writing` |

---

## Step 5: Chain Definitions Summary

### Stage 1: `data_management` — 1 chain

```
data_management_main (4 agents):
  util_punctuator → fa_glaser_data_classifier → segmentar_documento → fa_prime_mover_extractor
  max_retries: 3  timeout: 600s
```

### Stage 2: `open_coding` — 2 chains

```
open_coding_main (4 agents):
  fb_incident_grouper → fb_code_generator → fb_label_critic → fd_category_synthesizer
  max_retries: 3  timeout: 900s

open_coding_hypotheses (3 agents, parallel: true):
  fb_hypothesis_generator → fb_evidence_classifier → fd_hypothesis_synthesizer
  max_retries: 2  timeout: 600s
```

**Independent agents (not in any chain):**
- `fa_population_context` (runs before B1)
- `fd_config_critic` (sync point, depends on both chain outputs)
- `fc_main_concern_proposer` → `fc_main_concern_critic` (HITL gate pair)
- `population_generalizer`

### Stage 3: `selective_coding` — 6 chains

```
selective_main_concern (2 agents):
  fc_main_concern_proposer → fc_main_concern_critic
  max_retries: 3  timeout: 600s

selective_core_emergence (2 agents):
  fc_core_category_proposer → fc_core_emergence_critic
  max_retries: 3  timeout: 600s

selective_reduction (2 agents):
  fd_selective_reduction_proposer → fd_selective_reduction_critic
  max_retries: 3  timeout: 600s

selective_saturation (2 agents):
  fe_core_saturation_proposer → fe_core_saturation_critic
  max_retries: 3  timeout: 600s

selective_database_a (2 agents):
  ff_database_a_proposer → ff_database_a_critic
  max_retries: 3  timeout: 600s

selective_database_b (2 agents):
  ff_database_b_proposer → ff_database_b_critic
  max_retries: 3  timeout: 600s
```

**Note:** `selective_main_concern` references agents (`fc_main_concern_proposer` / `fc_main_concern_critic`) that exist in the `open_coding` stage in the current code. This discrepancy is intentional per the design document (MicroOrchestrators Part 4), where the `selective_coding_coordinator` wraps proposer→critic pairs. The actual agent lifecycle (which stage "owns" the agent) will be resolved by the ChainOrchestrator v3 backend integration.

### Stage 4: `theoretical_coding` — 1 chain

```
theoretical_coding (6 agents, parallel by default via shared dependency):
  f6b_ghost_blob_mapper, f6b_memo_theoretical_tagger, f6b_ecosystem_gap_detector,
  f6b_conceptual_elaborator, f6b_definition_writer, f6b_incident_elaborator
  max_retries: 2  timeout: 900s
```

### Stage 5: `writing` — 1 chain

```
writing_main (3 agents):
  f6a_natural_writer → f6a_writing_critic → f6a_gap_feeler
  max_retries: 3  timeout: 900s
```

---

## Step 6: New Helper Functions

```typescript
// Returns all chains for a given stage key
export function getStageChains(stageKey: string): ChainDef[] {
  const stage = PIPELINE_STAGES.find(s => s.key === stageKey);
  return stage?.chains || [];
}

// Looks up a chain by its canonical ID across all stages
export function getChainById(chainId: string): ChainDef | undefined {
  for (const stage of PIPELINE_STAGES) {
    if (stage.chains) {
      const chain = stage.chains.find(c => c.id === chainId);
      if (chain) return chain;
    }
  }
  return undefined;
}
```

### Verification matrix

| Test | Expected | How to verify |
|------|----------|---------------|
| `getStageChains("data_management")` | `[{ id: "data_management_main", ... }]` (length 1) | Unit test or console |
| `getStageChains("open_coding")` | 2 chains (`open_coding_main`, `open_coding_hypotheses`) | Unit test or console |
| `getStageChains("selective_coding")` | 6 chains | Unit test or console |
| `getStageChains("nonexistent")` | `[]` (empty, no error) | Unit test or console |
| `getChainById("open_coding_main")` | ChainDef with 4 agents | Unit test or console |
| `getChainById("open_coding_hypotheses")` | ChainDef with `parallel: true` | Unit test or console |
| `getChainById("nonexistent")` | `undefined` | Unit test or console |
| `PipelineAgents` rendering | Unchanged (uses `stage.agents`) | Visual inspection in browser |
| `Project.tsx` stage rendering | Unchanged (uses `stage.key`/`icon`/`label`) | Visual inspection in browser |
| `canRunAgent("util_punctuator", new Set())` | `true` (no deps) | Existing behavior |
| `areAllAgentsDone("data_management", doneSet)` | `true` if all 4 done | Existing behavior |

---

## Step 7: Backward Compatibility Guarantee

| What | Status |
|------|--------|
| `stage.agents` unchanged | ✅ All 5 stages keep their original `agents: AgentDef[]` |
| `canRunAgent()` works | ✅ Iterates `stage.agents` (unchanged) |
| `areAllAgentsDone()` works | ✅ Iterates `stage.agents` (unchanged) |
| `PipelineAgents.tsx` renders | ✅ Groups agents by `agent.chain` property (unchanged) |
| `Project.tsx` stage loop | ✅ Uses `PIPELINE_STAGES[].key`/`.icon`/`.label` (unchanged) |
| New `chains` field ignored by old code | ✅ Optional field — TypeScript `?.` safe |
