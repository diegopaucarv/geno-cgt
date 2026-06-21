# Prerequisite Change 8 — Frontend Preparation for chain_runs

> **Date:** 2026-06-21  
> **Status:** Implemented  
> **Scope:** Backend endpoint + Frontend API client + Placeholder UI component  

## Overview

Prepares the frontend to consume the `chain_runs` table that will be written by the ChainOrchestrator v3. This is a **pre-requisite** — the table does not exist yet, so the endpoint gracefully degrades to return `[]` when queried against a database without the table.

---

## Table of Contents

1. [Files Changed / Created](#files-changed--created)
2. [Step 1: Read Existing Files (Pre-Analysis)](#step-1-read-existing-files-pre-analysis)
3. [Step 2: Spillover Analysis](#step-2-spillover-analysis)
4. [Step 3: Pseudocode & Implementation Details](#step-3-pseudocode--implementation-details)
5. [Step 4: Pre-Evaluation](#step-4-pre-evaluation)
6. [Step 5: Post-Validation](#step-5-post-validation)
7. [Future Integration Checklist](#future-integration-checklist)

---

## Files Changed / Created

| File | Action | Description |
|------|--------|-------------|
| `backend/app/api/v1/chain_runs.py` | **Created** | FastAPI endpoint `GET /api/v1/projects/{project_id}/chain-runs` |
| `backend/app/main.py` | **Modified** | Registered `chain_runs.router` |
| `frontend/src/api/client.ts` | **Modified** | Added `ChainRunItem`, `AgentRunItem` interfaces + `getChainRuns()` |
| `frontend/src/components/ChainTimeline.tsx` | **Created** | Placeholder component (not wired to render tree) |
| `Documentacion/backend_gap_analysis/implementation/agent3_frontend_chainruns.md` | **Created** | This document |

---

## Step 1: Read Existing Files (Pre-Analysis)

### Files analyzed before implementation:

| File | Lines read | Key findings |
|------|-----------|--------------|
| `backend/app/api/v1/pipeline.py` | 1-24, 173-350, 1027-1079 | Router pattern: `APIRouter(prefix="/api/v1", tags=["pipeline"])`; auth via `Depends(get_current_user)`; DB via `Depends(get_db)`; raw SQL via `text()` |
| `backend/app/main.py` | 1-96 | Router registration: `app.include_router(pipeline.router)`; alphabetical import ordering |
| `frontend/src/api/client.ts` | 55-90, 1084-1147 | `request<T>()` helper pattern with token injection; async functions take projectId + params, call `request()` |
| `frontend/src/config/pipelineChains.ts` | 1-416 | Existing `AgentDef`, `StageDef`, `PIPELINE_STAGES` — provides agent labels for future timeline |
| `backend/app/db/database.py` | 1-24 | `get_db()` dependency returns `AsyncSession` |
| `backend/app/models/base.py` | 1-24 | `Base(DeclarativeBase)`, `TimestampMixin` |
| `backend/app/models/exec_log.py` | 1-25 | JSONB column usage: `mapped_column(JSONB, default=dict)` |
| `frontend/src/pages/Project.tsx` | 1-80 | Import pattern for `ChainTimeline` (future) — imports from `../api/client` and `../components/*` |

### Key patterns identified:

1. **Backend router**: Uses `APIRouter(prefix="/api/v1", tags=["..."])` with endpoint functions decorated by `@router.get(...)` / `@router.post(...)`.
2. **Auth**: Every endpoint takes `current_user: Usuario = Depends(get_current_user)`.
3. **Database**: Raw SQL queries via `text()` are common when no SQLAlchemy model exists (e.g., `get_pipeline_log` in pipeline.py).
4. **Frontend client**: `request<T>(path, options)` handles auth headers, token refresh, and error extraction. All API functions return `Promise<T>`.
5. **Component imports**: Named exports from `../api/client` and default exports from `../components/*`.

---

## Step 2: Spillover Analysis

### Q1: Does the new endpoint conflict with any existing route?

**No.** The new route is:

```
GET /api/v1/projects/{project_id}/chain-runs
```

Existing routes in `pipeline.py` use the pattern:

```
GET  /api/v1/projects/{project_id}/pipeline/log
GET  /api/v1/projects/{project_id}/pipeline/decisions
GET  /api/v1/projects/{project_id}/pipeline/status
POST /api/v1/projects/{project_id}/pipeline/run-stage/{stage_name}
POST /api/v1/projects/{project_id}/pipeline/run
GET  /api/v1/projects/{project_id}/pipeline/logs/stream
GET  /api/v1/projects/{project_id}/agent-logs
GET  /api/v1/projects/{project_id}/agent-memos
...
```

The `chain-runs` route is at the `/projects/{project_id}/` level (NOT nested under `/pipeline/`), so it **cannot collide** with any existing pipeline route. It also does not match any existing path pattern.

### Q2: Where exactly should the new `getChainRuns` function go in client.ts?

**Decision:** After `getPipelineDecisions()` (line ~1101), before the "Agent Log Types" section.

**Rationale:**
- `getPipelineDecisions` is the last "pipeline" related function
- The "Chain Runs" section is conceptually related to pipeline execution
- The "Agent Log Types" section that follows is a separate concern
- Adding a new `// ── Chain Runs ──` section block matches the existing convention

### Q3: Should the endpoint be in `pipeline.py` or its own file?

**Decision:** New file `backend/app/api/v1/chain_runs.py`.

**Rationale:**
- `pipeline.py` is already 1,079 lines and covers pipeline execution and status
- `chain_runs` is a separate concept (execution history, not execution triggers)
- The ChainOrchestrator v3 is a distinct architectural component
- Future: more chain_runs endpoints (e.g., `GET /chain-runs/{run_id}`, `POST /chain-runs/{run_id}/retry`) would bloat pipeline.py further
- Consistent with existing pattern: `hitl.py`, `memos.py`, `analysis.py` are all separate files

---

## Step 3: Pseudocode & Implementation Details

### 3.1 Backend Endpoint (`backend/app/api/v1/chain_runs.py`)

```
ROUTER: APIRouter(prefix="/api/v1", tags=["chain_runs"])

SCHEMAS:
  AgentRunResponse:
    agent_id: str
    attempt_number: int
    output: dict
    tokens_used: int
    tool_calls_count: int
    retry_count: int
    orchestrator_action: str
    started_at: str | None
    finished_at: str | None

  ChainRunResponse:
    id: str
    project_id: str
    chain_id: str
    parent_chain_run_id: str | None
    status: str
    agent_runs: list[AgentRunResponse] | None
    total_tokens: int
    total_retries: int
    started_at: str | None
    finished_at: str | None
    created_by: str
    created_at: str | None

ENDPOINT: GET /projects/{project_id}/chain-runs
  PARAMS:
    chain_id: str | None = Query(None)
    limit: int = Query(20, ge=1, le=100)
    include_agent_runs: bool = Query(True)
  DEPENDENCIES:
    db: AsyncSession = Depends(get_db)
    current_user: Usuario = Depends(get_current_user)

  LOGIC:
    1. Build SELECT clause (omit agent_runs column if include_agent_runs=False)
    2. Build WHERE clause (project_id required, chain_id optional)
    3. Execute raw SQL query on chain_runs table
    4. CATCH exception → return [] (table may not exist yet)
    5. Map rows → ChainRunResponse (parse JSONB agent_runs safely)
    6. Return list[ChainRunResponse]
```

#### Key design decisions:

1. **Graceful degradation**: If `chain_runs` table doesn't exist, return `[]` rather than 500. This allows deployment before the ChainOrchestrator v3 creates the table.

2. **JSONB parsing safety**: The `agent_runs` column is JSONB. PostgreSQL's asyncpg driver returns it as a Python `list`. But as a safety net, the code handles both `list` and `str` (with `json.loads` fallback), and catches `JSONDecodeError`.

3. **Conditional column selection**: When `include_agent_runs=False`, the SELECT uses `NULL::jsonb AS agent_runs` to avoid sending potentially large JSONB arrays. This is important for UI components that only need metadata (count, status).

4. **Raw SQL (text())**: No SQLAlchemy model exists for `chain_runs`. Using raw SQL avoids creating a model that would fail on startup if the table doesn't exist. Later, a model can be added and the endpoint refactored.

### 3.2 Frontend API Client (`frontend/src/api/client.ts`)

```
INTERFACES:
  AgentRunItem:
    agent_id: string
    attempt_number: number
    output: Record<string, any>
    tokens_used: number
    tool_calls_count: number
    retry_count: number
    orchestrator_action: "proceed" | "force_proceed" | "skip"
    started_at: string | null
    finished_at: string | null

  ChainRunItem:
    id: string
    project_id: string
    chain_id: string
    parent_chain_run_id: string | null
    status: "running" | "completed" | "aborted" | "paused_hitl"
    agent_runs: AgentRunItem[] | null
    total_tokens: number
    total_retries: number
    started_at: string | null
    finished_at: string | null
    created_by: string
    created_at: string | null

FUNCTION:
  getChainRuns(projectId, chainId?, limit?, includeAgentRuns?): Promise<ChainRunItem[]>
    1. Build URLSearchParams from optional params
    2. Default include_agent_runs to true
    3. Call request<ChainRunItem[]>(`/projects/${projectId}/chain-runs?${params}`)
```

#### Key design decisions:

1. **`orchestrator_action` as union type**: Using `"proceed" | "force_proceed" | "skip"` rather than `string` gives TypeScript-level safety and autocompletion.

2. **`status` as union type**: Same rationale — `"running" | "completed" | "aborted" | "paused_hitl"` prevents typos.

3. **`includeAgentRuns` parameter**: Allows callers to request lighter payloads for list views. Default `true` matches the backend default.

4. **No `retries` field in `AgentRunItem`**: Per ChainOrchestrator v3 spec, only successful runs are persisted. Failures are tracked by `retry_count` and exist in `conversation_history` in memory during execution.

### 3.3 Placeholder Component (`frontend/src/components/ChainTimeline.tsx`)

```
PROPS:
  ChainTimelineProps:
    chainRuns: ChainRunItem[]
    chainFilter?: string

INTERNAL:
  statusIcon(status): string     → maps status → emoji icon
  agentActionLabel(action): string → maps orchestrator_action → emoji

RENDER:
  IF filtered.length === 0:
    → "No chain runs recorded yet."
  ELSE:
    → "🔗 Chain History — Coming Soon" bordered panel
    → For each chain run:
      - Status icon + chain_id + status label
      - Summary line (tokens, retries, started_at)
      - Agent runs list (agent_id, attempt, tokens, retry count)
    → Commented-out pseudocode for full timeline (200+ lines in comments)
```

#### Key design decisions:

1. **Not wired to render tree**: The component is importable from `Project.tsx` but NOT rendered. This prevents the "Coming Soon" message from appearing to users prematurely.

2. **Rich commented-out pseudocode**: The full timeline rendering plan is documented as a code comment inside the component. This serves as a specification for the developer who implements the actual UI. Includes:
   - Visual mockup of target rendering
   - Implementation plan (7 numbered steps)
   - Executable pseudocode showing component hierarchy

3. **`chainFilter` prop**: Allows the component to display runs for a specific chain (e.g., only "open_coding_main") or all chains.

4. **Graceful empty state**: Shows a friendly message instead of crashing when `chainRuns` is empty.

---

## Step 4: Pre-Evaluation

### Q1: Will the endpoint work with an EMPTY chain_runs table?

**YES.** The endpoint uses raw SQL `SELECT ... FROM chain_runs WHERE ...`. If the table exists but is empty, the query returns zero rows → endpoint returns `[]`. The `row._mapping` iteration loop never executes.

### Q2: What happens if the chain_runs table doesn't exist at all?

**Graceful degradation to `[]`.** The query is wrapped in a `try/except Exception` block:

```python
try:
    result = await db.execute(query, params)
    rows = result.fetchall()
except Exception as e:
    logger.warning(f"chain_runs query failed (table may not exist yet): {e}")
    return []
```

This means:
- The API returns 200 with `[]` (not 500)
- The frontend receives an empty array (not an error)
- The Timeline component shows "No chain runs recorded yet."
- No deployment ordering dependency — the endpoint works before, during, and after the ChainOrchestrator v3 migration

### Q3: What happens if agent_runs JSONB is malformed?

**Safe fallback.** The `AgentRunResponse` mapping code handles this:

```python
if isinstance(agent_runs_raw, str):
    import json
    try:
        agent_runs_raw = json.loads(agent_runs_raw)
    except (json.JSONDecodeError, TypeError):
        agent_runs_raw = []

if isinstance(agent_runs_raw, list):
    agent_runs_parsed = []
    for ar in agent_runs_raw:
        if isinstance(ar, dict):
            agent_runs_parsed.append(AgentRunResponse(...))
```

Each agent run entry is validated:
- Non-dict entries in the JSONB array are silently skipped
- Missing fields default to sensible values (`agent_id=""`, `attempt_number=1`, `tokens_used=0`)
- `orchestrator_action` defaults to `"proceed"`

This is intentionally lenient — the ChainOrchestrator v3 is the canonical writer and should produce valid data. The reader (this endpoint) should be resilient to edge cases.

### Q4: Does the frontend compile with the new interfaces (even if unused)?

**YES.** The new interfaces and function are:
- Added to `client.ts` with valid TypeScript syntax
- `ChainTimeline.tsx` imports from `../api/client` correctly
- Neither is referenced in any other file yet
- TypeScript allows unused exports — they're just part of the module's public API

The `ChainTimeline` component is a module with a default export. It's not imported in `Project.tsx` yet, so it won't be included in any bundle (tree-shaking) but will compile cleanly.

---

## Step 5: Post-Validation

### 5.1 Testing the Endpoint with curl

**Prerequisite:** Backend must be running.

```bash
# Test with empty table (or no table yet)
curl -s http://localhost:8000/api/v1/projects/{PROJECT_ID}/chain-runs \
  -H "Authorization: Bearer {TOKEN}" | jq '.'
# Expected: []  (graceful degradation)

# Test with chain_id filter
curl -s "http://localhost:8000/api/v1/projects/{PROJECT_ID}/chain-runs?chain_id=open_coding_main" \
  -H "Authorization: Bearer {TOKEN}" | jq '.'
# Expected: []

# Test without agent_runs (lighter payload)
curl -s "http://localhost:8000/api/v1/projects/{PROJECT_ID}/chain-runs?include_agent_runs=false" \
  -H "Authorization: Bearer {TOKEN}" | jq '.'
# Expected: []  (agent_runs field should be null per response model, though empty list from SQL will show null)

# Test with limit
curl -s "http://localhost:8000/api/v1/projects/{PROJECT_ID}/chain-runs?limit=5" \
  -H "Authorization: Bearer {TOKEN}" | jq '.'
# Expected: []

# Test unauthenticated
curl -s http://localhost:8000/api/v1/projects/{PROJECT_ID}/chain-runs | jq '.'
# Expected: {"detail": "Not authenticated"}  (401)

# Verify Swagger docs
# Open http://localhost:8000/docs → should show "chain_runs" tag with the new endpoint
```

### 5.2 Verifying TypeScript Compilation

```bash
cd /mnt/hdd/Program\ Files/Docker/gt/frontend

# TypeScript type-check only (no emit)
npx tsc --noEmit

# Expected: no errors related to ChainRunItem, AgentRunItem, getChainRuns, or ChainTimeline

# If using rsbuild, build check:
npx rsbuild build
```

### 5.3 Verifying the Placeholder Component Renders

**Method 1: Temporary test import in Project.tsx**

Add this temporarily to `Project.tsx` to verify rendering:

```tsx
import ChainTimeline from "../components/ChainTimeline";
import { getChainRuns, type ChainRunItem } from "../api/client";

// Inside the component:
const [chainRuns, setChainRuns] = useState<ChainRunItem[]>([]);

useEffect(() => {
  if (id) getChainRuns(id).then(setChainRuns).catch(() => {});
}, [id]);

// In JSX:
<ChainTimeline chainRuns={chainRuns} />
```

**Method 2: Unit test (future)**

```tsx
// ChainTimeline.test.tsx
import { render, screen } from "@testing-library/react";
import ChainTimeline from "./ChainTimeline";

test("renders empty state", () => {
  render(<ChainTimeline chainRuns={[]} />);
  expect(screen.getByText(/no chain runs/i)).toBeInTheDocument();
});

test("renders coming soon banner", () => {
  render(<ChainTimeline chainRuns={[{ id: "1", chain_id: "test", status: "completed", ... }]} />);
  expect(screen.getByText(/coming soon/i)).toBeInTheDocument();
});
```

### 5.4 Verifying Router Registration

```bash
# Check that the router is imported and registered
grep -n "chain_runs" /mnt/hdd/Program\ Files/Docker/gt/backend/app/main.py
# Expected: lines showing import and app.include_router(chain_runs.router)
```

---

## Future Integration Checklist

When the ChainOrchestrator v3 is ready and `chain_runs` table exists with data:

- [ ] **Wire `ChainTimeline` into `Project.tsx`** — add import and render in the pipeline section
- [ ] **Add retry-from-here UI** — button on each agent row triggers branching retry
- [ ] **Create SQLAlchemy model** for `chain_runs` table (replace raw SQL in endpoint)
- [ ] **Add `GET /chain-runs/{run_id}` endpoint** — single run detail with full agent_runs
- [ ] **Add `POST /chain-runs/{run_id}/retry` endpoint** — triggers branching retry from a specific agent
- [ ] **Add real-time updates** — WebSocket or polling for `status: "running"` chains
- [ ] **Add filtering by `created_by`** — distinguish system runs from user-initiated retries
- [ ] **Add pagination** — cursor-based for large project histories
- [ ] **Add sorting options** — by tokens, retries, run duration
- [ ] **Style the timeline** — match the visual mockup in the pseudocode comments

---

## Summary

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Endpoint location | New file `chain_runs.py` | Separate concern from `pipeline.py`; room for future growth |
| Router prefix | `/api/v1` (same as others) | Consistent with all existing routers |
| Query method | Raw SQL `text()` | No SQLAlchemy model yet; avoids startup errors |
| Empty table behavior | Return `[]` (200 OK) | Graceful degradation; no deployment ordering |
| Agent runs parsing | Lenient with defaults | Resilient to edge cases in JSONB |
| Frontend types | Union types for status/action | TypeScript safety and autocomplete |
| Component status | Placeholder, not wired | Prevents premature UI; importable for testing |
| Pseudocode | Commented in component | Serves as spec for future developer |

### Files to review:

- `backend/app/api/v1/chain_runs.py` — 184 lines, new file
- `backend/app/main.py` — +2 lines (import + router registration)
- `frontend/src/api/client.ts` — +42 lines (interfaces + function)
- `frontend/src/components/ChainTimeline.tsx` — 204 lines, new file (placeholder)
