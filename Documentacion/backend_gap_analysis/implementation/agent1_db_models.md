# Agent 1: Prerequisite Changes 1, 4, 5, 6 — Implementation Analysis

> **Status:** Complete analysis for four structural prerequisite changes of ChainOrchestrator v3.
> **Generated:** 2026-06-21
> **Reference:** `7-MicroOrchestrators-Final.md` lines 124-448, 58-101

---

## 1. Requirements Diagnosis

### CHANGE 1: `chain_runs` Database Table

**What:** A new table tracking execution history of agent chains, with branching support via `parent_chain_run_id`.

**Dependencies:**
- PostgreSQL `gen_random_uuid()` extension (already available — used in `proyectos` via Python-side `uuid.uuid4`)
- Foreign key on `proyectos.id` (table already exists)
- Self-referential FK on `parent_chain_run_id` (only possible after table creation, but migration handles this inline)
- JSONB column type (already used extensively in `pipeline_run.py`, `agent_outputs.py`)

**Design mismatch to resolve:**
| Aspect | Design SQL | Existing Codebase Convention | Resolution |
|--------|-----------|------------------------------|------------|
| `id` default | `DEFAULT gen_random_uuid()` | `default=uuid.uuid4` (Python-side) | Use Python-side `default=uuid.uuid4` in model; add `server_default=sa.text("gen_random_uuid()")` in migration for defense-in-depth |
| `created_at` | `TIMESTAMPTZ DEFAULT now()` | `TimestampMixin.creado_en` uses `server_default=func.now()` | Use `TimestampMixin` to inherit `creado_en` + `actualizado_en` pattern. `started_at` is separate (agent-side timestamp), so we keep both |
| `status` default | `'running'` | String(20) pattern from PipelineRun | Use `String(20)` with `default='running'` |
| `agent_runs` default | `'[]'` | JSONB columns in codebase use `default=dict` or `default=list` | Use `default=list` (SQLAlchemy serializes to `'[]'`) |

**Key decision:** The model inherits from `Base` and `TimestampMixin` (consistent with every model in the codebase). The `creado_en` / `actualizado_en` columns from `TimestampMixin` provide DB-level timestamps, while `started_at` / `finished_at` are application-level timestamps set by the orchestrator.

### CHANGE 4: `ToolCache` Class

**What:** In-memory cache keyed by `(tool_name, params)`. Avoids re-executing tool calls during retries.

**Dependencies:** None. Pure Python, no imports beyond `json` and `typing`.

**Risk:** In-memory means it's lost across Celery worker restarts. This is intentional — the cache is scoped to a single chain execution, not cross-chain. The design explicitly says "during a chain execution."

### CHANGE 5: `ChainState`, `AgentRun`, `ChainRun` Dataclasses

**What:** Three pure-Python dataclasses defining the state model for the orchestrator.

**Dependencies:** None external. Only `dataclasses`, `time` (for `ChainState.elapsed` property).

**Design notes:**
- `ChainState.start_time` uses `time.monotonic()` — NOT `time.time()`. This is important because `time.monotonic()` is immune to system clock changes. Existing code in `base.py` uses `time.time()` for `started_at = time.time()` in `BaseAgent.run()`. The orchestrator will need to reconcile this (but that's agent2's task).
- `AgentRun.output` is typed as `dict` (not `AgentOutput` or `AgentResult`). This is intentional — it stores only the final successful `data` dict from `AgentResult.data`.
- `ChainRun.agent_runs` is typed as `list[AgentRun]` — only successful outputs, in order.
- All timestamp fields (`started_at`, `finished_at`) are ISO strings, not `datetime` objects. This matches the pattern in `AgentLoopLog` (base.py lines 153, 155: `started_at: str`, `finished_at: str`).

### CHANGE 6: `ChainOrchestrator.decide()`

**What:** A ~30-line pure function implementing routing logic. 6 branches based on `suggested_action` from the agent's self-evaluation.

**Dependencies:**
- `AgentOutput` with `self_eval` field (must have `suggested_action` and `retry_reason` attributes)
- `ChainState` (from Change 5)
- `self.max_retries` (class attribute, default 3)

**Design note:** The class `ChainOrchestrator` must be defined first (even if minimal) to house `decide()`. The full class implementation is for agent2. We create the shell class with `max_retries` and `decide()`.

**Branch coverage of `decide()`:**

| Input `suggested_action` | Condition | Output `action` | Output `reason` |
|--------------------------|-----------|-----------------|-----------------|
| any | `elapsed > timeout` | `"abort"` | `"Timeout: chain exceeded time limit"` |
| `"proceed"` | — | `"proceed"` | `None` |
| `"retry"` | `retry_count < 3` | `"retry"` | `agent_output.self_eval.retry_reason` |
| `"retry"` | `retry_count >= 3` | `"force_proceed"` | `"Max retries (3) reached"` |
| `"escalate_to_hitl"` | — | `"pause_hitl"` | `agent_output.self_eval.retry_reason` |
| `"skip"` | — | `"skip"` | `None` |
| `"abort"` | — | `"abort"` | `agent_output.self_eval.retry_reason` |
| unknown/None | — | `"proceed"` | `None` (fallback) |

---

## 2. Spillover Map

### Files Created (new)

| File | Change | Content |
|------|--------|---------|
| `backend/app/models/domain/chain_run.py` | C1 | `ChainRun` SQLAlchemy model |
| `backend/migrations/versions/NNN_chain_runs.py` | C1 | Alembic migration |
| `backend/app/agents/tool_cache.py` | C4 | `ToolCache` class |
| `backend/app/agents/chain_orchestrator.py` | C5 + C6 | `ChainState`, `AgentRun`, `ChainRun` dataclasses + `ChainOrchestrator` shell class with `decide()` |

### Files Modified (existing)

| File | Change | What changes |
|------|--------|-------------|
| `backend/migrations/env.py` | C1 | Add `from app.models.domain.chain_run import ChainRun` to the import block (lines 33-77) |
| `backend/app/agents/__init__.py` | C4 + C5 | Add `ToolCache`, `ChainOrchestrator`, `ChainState`, `AgentRun`, `ChainRun` exports |
| `backend/app/models/__init__.py` | C1 | (Optional — currently empty, no pattern of re-exporting models exists) |

### Files Verified (no changes needed)

| File | Reason |
|------|--------|
| `backend/app/models/domain/pipeline_run.py` | Contains `PipelineRun` which `chain_runs` is modeled after. No conflict — separate tables. |
| `backend/app/agents/base.py` | `AgentResult`, `AgentLoopLog` — no naming conflict with new `AgentRun`, `ChainRun`. `AgentLoopLog` is a log dataclass; `AgentRun` is an execution record. |
| `backend/app/agents/orchestrator.py` | Existing `OrchestratorRuleEngine` is a different orchestrator (pipeline step routing). `ChainOrchestrator` is a separate agent-chain orchestrator. Naming is deliberately distinct. |
| `backend/app/services/pipeline_orchestrator.py` | Uses `PipelineRun` only. No overlap with `chain_runs`. |
| `backend/app/agents/tools/context_window.py` | Uses `BatchExecution` from `pipeline_run.py`. No change needed. |

### Migration Chain Analysis

```
f67d172dd775 (initial_schema) 
  → ... → 015 (add_source_memo_to_theoretical_codes)
        → a26195ceb7f0 (batch_and_hitl)
              → eba2e69cb207 (merge_a01_and_a02)
                    → (a01_database_edges_free_text, a02_sort_order)

Latest leaf: 015 (down_revision = "a26195ceb7f0")
```

**Our migration must declare:** `down_revision = "015"`

---

## 3. Pseudocode Mockups

### CHANGE 1: `chain_run.py` — SQLAlchemy Model

```python
# backend/app/models/domain/chain_run.py
"""ChainRun — tracking de ejecuciones del ChainOrchestrator v3.

Cada fila representa un 'commit' en el historial de ejecución
de cadenas de agentes, con soporte de branching vía parent_chain_run_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class ChainRunModel(Base, TimestampMixin):
    """Registro de ejecución de una cadena de agentes.
    
    Equivalente a un 'PipelineRun' pero para el ChainOrchestrator v3.
    Soporta branching: un chain_run puede tener un parent_chain_run_id
    que apunta a otro chain_run (ej. split para explorar hipótesis alternativas).
    """
    
    __tablename__ = "chain_runs"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    
    # ── Identificación ──────────────────────────────────────────────
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE"), nullable=False
    )
    chain_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Identificador de la cadena (ej. 'open_coding_main')"
    )
    parent_chain_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chain_runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="Para branching: apunta al chain_run padre"
    )
    
    # ── Estado ─────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running",
        comment="running | completed | aborted | paused_hitl"
    )
    
    # ── Payload ────────────────────────────────────────────────────
    agent_runs: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="Lista de AgentRun (solo outputs exitosos, en orden)"
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Suma de tokens de todos los agent_runs"
    )
    total_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Suma de retry_count de todos los agent_runs"
    )
    
    # ── Timestamps de ejecución ────────────────────────────────────
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow,
        comment="Timestamp de inicio de la cadena (aplicación)"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp de finalización (null si running/paused_hitl)"
    )
    
    # ── Auditoría ──────────────────────────────────────────────────
    created_by: Mapped[str] = mapped_column(
        String(100), nullable=False, default="system",
        comment="Quién disparó la cadena: 'system' o 'user:{user_id}'"
    )
    # creado_en y actualizado_en vienen de TimestampMixin
```

**Design decisions explained:**
1. **Class name `ChainRunModel`** — The dataclass in Change 5 is also called `ChainRun`. Using `ChainRunModel` for the SQLAlchemy model avoids name collision in the same namespace. In the migration `env.py` it will be imported as `ChainRunModel`.
2. **`started_at` uses `DateTime(timezone=True)` + `default=datetime.utcnow`** — Follows the pattern in `BatchExecution` (pipeline_run.py line 131: `DateTime(timezone=True), nullable=True, default=None`). But since our schema requires `NOT NULL DEFAULT now()`, we use `default=datetime.utcnow` for Python-side default. The migration adds `server_default=sa.text("now()")`.
3. **`created_by` is `String(100)`** — Not `String(50)` because user IDs can be prefixed like `"user:{user_id}"` which can be longer than 50 chars.
4. **`TimestampMixin` provides `creado_en` / `actualizado_en`** — Standard in all models. These track when the row was created/updated in the DB, separate from `started_at`/`finished_at` which track when the chain actually started/finished executing.

### CHANGE 1: Migration File

```python
# backend/migrations/versions/NNN_chain_runs.py
"""chain_runs

Revision ID: {auto_generated}
Revises: 015
Create Date: 2026-06-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "{auto_generated}"
down_revision: Union[str, Sequence[str], None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chain_runs",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("chain_id", sa.String(length=100), nullable=False),
        sa.Column("parent_chain_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "agent_runs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "total_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_retries",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.String(length=100),
            nullable=False,
            server_default="system",
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["proyectos.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_chain_run_id"],
            ["chain_runs.id"],
            ondelete="SET NULL",
        ),
    )

    # ── Índices ──
    op.create_index(
        "idx_chain_runs_project",
        "chain_runs",
        ["project_id"],
    )
    op.create_index(
        "idx_chain_runs_chain_id",
        "chain_runs",
        ["chain_id"],
    )
    op.create_index(
        "idx_chain_runs_status",
        "chain_runs",
        ["status"],
    )
    op.create_index(
        "idx_chain_runs_parent",
        "chain_runs",
        ["parent_chain_run_id"],
        unique=False,
        postgresql_where=sa.text("parent_chain_run_id IS NOT NULL"),
    )
    op.create_index(
        "idx_chain_runs_created_at",
        "chain_runs",
        ["project_id", sa.text("creado_en DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_chain_runs_created_at", table_name="chain_runs")
    op.drop_index("idx_chain_runs_parent", table_name="chain_runs")
    op.drop_index("idx_chain_runs_status", table_name="chain_runs")
    op.drop_index("idx_chain_runs_chain_id", table_name="chain_runs")
    op.drop_index("idx_chain_runs_project", table_name="chain_runs")
    op.drop_table("chain_runs")
```

### CHANGE 4: `tool_cache.py`

```python
# backend/app/agents/tool_cache.py
"""ToolCache: caché en memoria para tool calls durante una ejecución de cadena.

Evita re-ejecutar tools durante retries de agentes. El caché se limpia
al finalizar la cadena. No es compartido entre workers ni cadenas diferentes.
"""

from __future__ import annotations

import json
from typing import Any


class ToolCache:
    """Caché en memoria keyed por (tool_name, params) serializados.
    
    Uso típico:
        cache = ToolCache()
        result = cache.get("search_segments", {"query": "x", "top_k": 5})
        if result is None:
            result = registry.execute("search_segments", ...)
            cache.set("search_segments", {"query": "x", "top_k": 5}, result)
    """
    
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
    
    def get(self, tool_name: str, params: dict[str, Any]) -> Any | None:
        """Obtiene resultado cacheado, o None si no existe."""
        key = json.dumps({"tool": tool_name, "params": params}, sort_keys=True)
        return self._cache.get(key)
    
    def set(self, tool_name: str, params: dict[str, Any], result: Any) -> None:
        """Almacena resultado en caché."""
        key = json.dumps({"tool": tool_name, "params": params}, sort_keys=True)
        self._cache[key] = result
    
    def clear(self) -> None:
        """Limpia el caché."""
        self._cache.clear()
    
    def __len__(self) -> int:
        return len(self._cache)
```

### CHANGE 5 + 6: `chain_orchestrator.py`

```python
# backend/app/agents/chain_orchestrator.py
"""ChainOrchestrator v3: orquestador ultra-ligero de cadenas de agentes.

Proporciona:
- ChainState: estado mínimo de la cadena (tiempo, tokens)
- AgentRun: registro de UNA ejecución exitosa de un agente
- ChainRun: un 'commit' en el historial de ejecución
- ChainOrchestrator: lógica de routing (decide)

Principio: Zero Dependencies. Sin imports de SQLAlchemy, Celery, ni LLM clients.
El orquestador es una máquina de estados pura que solo toma decisiones
basadas en los contadores internos y el self_eval del agente.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


# ═══════════════════════════════════════════════════════════════════
# Dataclasses (Change 5)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ChainState:
    """Estado mínimo de la cadena para decisiones del orquestador."""
    
    start_time: float          # time.monotonic() al iniciar
    timeout_seconds: float     # timeout duro (default: 600s)
    total_tokens: int = 0      # solo medir, no decidir

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_time


@dataclass
class AgentRun:
    """Registro de UNA ejecución exitosa de un agente."""
    
    agent_id: str
    attempt_number: int          # 1 = primer intento, 2 = primer retry, etc.
    output: dict                 # AgentOutput.data (solo el exitoso)
    tokens_used: int             # Tokens consumidos en el intento exitoso
    tool_calls_count: int        # Total de tool calls (incluye cache hits)
    retry_count: int             # Intentos fallidos antes de este exitoso
    orchestrator_action: str     # "proceed" | "force_proceed" | "skip"
    started_at: str              # ISO timestamp
    finished_at: str             # ISO timestamp


@dataclass
class ChainRun:
    """Un 'commit' en el historial de ejecución de cadenas."""
    
    chain_id: str                # "open_coding_main", "open_coding_hypotheses", etc.
    project_id: str              # UUID
    parent_chain_run_id: str | None  # Para branching
    status: str                  # "completed" | "aborted" | "paused_hitl" | "running"
    agent_runs: list[AgentRun]   # Solo outputs exitosos, en orden
    total_tokens: int            # Suma de tokens de todos los agent_runs
    total_retries: int           # Suma de retry_count de todos los agent_runs
    started_at: str              # ISO timestamp
    finished_at: str | None      # None si running/paused_hitl
    created_by: str              # "system" | "user:{user_id}"


# ═══════════════════════════════════════════════════════════════════
# ChainOrchestrator (Change 6)
# ═══════════════════════════════════════════════════════════════════


class ChainOrchestrator:
    """Orquestador ultra-ligero para cadenas de agentes.
    
    Principios:
    - Sin estado mutable interno (el estado vive en ChainState/ChainRun)
    - decide() es una función pura: mismos inputs → mismo output
    - No usa LLM para routing — las decisiones son determinísticas
    - max_retries es configurable (default: 3)
    """
    
    def __init__(self, max_retries: int = 3) -> None:
        """Inicializa el orquestador.
        
        Args:
            max_retries: Número máximo de retries por agente (default: 3).
        """
        self.max_retries = max_retries
    
    def decide(
        self,
        agent_output: Any,
        retry_count: int,
        chain_state: ChainState,
    ) -> tuple[str, str | None]:
        """Toma una decisión de routing basada exclusivamente en
        suggested_action del agente + contadores del orquestador.
        
        Args:
            agent_output: AgentOutput con self_eval
            retry_count: int — intentos acumulados para este agente (0-based)
            chain_state: ChainState con elapsed, timeout_seconds
        
        Returns:
            (action: str, reason: str | None)
        """
        action = agent_output.self_eval.suggested_action

        # Timeout → aborta todo
        if chain_state.elapsed > chain_state.timeout_seconds:
            return "abort", "Timeout: chain exceeded time limit"

        # El agente quiere proceder → adelante
        if action == "proceed":
            return "proceed", None

        # El agente quiere retry → solo si no excedió el límite
        if action == "retry":
            if retry_count < self.max_retries:
                return "retry", agent_output.self_eval.retry_reason
            else:
                return (
                    "force_proceed",
                    f"Max retries ({self.max_retries}) reached",
                )

        # El agente pide HITL → pausar
        if action == "escalate_to_hitl":
            return "pause_hitl", agent_output.self_eval.retry_reason

        # Skip → siguiente agente
        if action == "skip":
            return "skip", None

        # Abort → detener todo
        if action == "abort":
            return "abort", agent_output.self_eval.retry_reason

        # Fallback (no debería ocurrir): agente sin self_eval o acción desconocida
        return "proceed", None
```

---

## 4. Insertion Points

### 4.1 New Files (exact paths)

| File | Full Path |
|------|-----------|
| ChainRun model | `/mnt/hdd/Program Files/Docker/gt/backend/app/models/domain/chain_run.py` |
| Migration | `/mnt/hdd/Program Files/Docker/gt/backend/migrations/versions/NNN_chain_runs.py` |
| ToolCache | `/mnt/hdd/Program Files/Docker/gt/backend/app/agents/tool_cache.py` |
| ChainOrchestrator | `/mnt/hdd/Program Files/Docker/gt/backend/app/agents/chain_orchestrator.py` |

### 4.2 Migration `env.py` — Add Import

**File:** `/mnt/hdd/Program Files/Docker/gt/backend/migrations/env.py`
**Position:** Line 52 (after the `PipelineRun, PipelineTask, TaskStepCheckpoint` import)

```python
# EXISTING (line 51-55):
from app.models.domain.pipeline_run import (
    PipelineRun,
    PipelineTask,
    TaskStepCheckpoint,
)

# ADD after line 55:
from app.models.domain.chain_run import ChainRunModel
```

This follows the exact same pattern as every other domain model import in `env.py`. The import ensures Alembic can detect schema changes via `target_metadata = Base.metadata`.

### 4.3 Agents `__init__.py` — Add Exports

**File:** `/mnt/hdd/Program Files/Docker/gt/backend/app/agents/__init__.py`
**Position:** After line 22 (the `tool_registry` import), and in `__all__` list after line 37

```python
# ADD import (after existing tool_registry import, line 22):
from app.agents.chain_orchestrator import (
    AgentRun,
    ChainOrchestrator,
    ChainRun,
    ChainState,
)
from app.agents.tool_cache import ToolCache

# ADD to __all__ list (after line 37, before closing bracket):
    "AgentRun",
    "ChainOrchestrator",
    "ChainRun",
    "ChainState",
    "ToolCache",
```

### 4.4 Models `__init__.py` — No Change Needed

**File:** `/mnt/hdd/Program Files/Docker/gt/backend/app/models/__init__.py`
**Current content:** Empty file.
**Decision:** Leave empty. The codebase pattern is to import domain models directly from their module files (e.g., `from app.models.domain.pipeline_run import PipelineRun`). No centralized re-export exists.

---

## 5. Pre-Implementation Evaluation

### 5.1 Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Name collision: `ChainRun` (dataclass) vs `ChainRunModel` (SQLAlchemy)** | Low | The dataclass lives in `agents/chain_orchestrator.py`; the model lives in `models/domain/chain_run.py`. Different modules, no import conflict. |
| **Migration order: wrong `down_revision`** | Medium | Verified: `015` is the latest leaf. Verified by grepping all migration files for `down_revision` chains. |
| **Self-referential FK creates circular dependency in migration** | Low | PostgreSQL resolves this at table creation time. Alembic handles it correctly as long as the FK is defined in the same `create_table()` call (which it is). |
| **`created_by: 'system'` vs `'user:{user_id}'` — max length** | Low | User UUIDs are 36 chars, so `"user:" + 36 = 42` chars. `String(100)` provides ample headroom. |
| **`agent_runs` JSONB default `'[]'` in migration vs `default=list` in model** | Low | SQLAlchemy model uses `default=list` which serializes to `'[]'`. Migration uses `server_default="'[]'::jsonb"`. Both produce empty JSON array. |
| **`started_at` and `TimestampMixin.creado_en` both default to `now()`** | Info | These are intentionally different timestamps: `started_at` is when the chain *began executing* (set by the orchestrator), `creado_en` is when the row was *inserted into the DB* (set by PostgreSQL). They may differ by milliseconds. |

### 5.2 Will This Break Existing Tests?

**No.** All changes are additive:
- C1: New table, new model. No existing code queries `chain_runs`.
- C4: New class, no callers yet.
- C5: New dataclasses, no callers yet.
- C6: New method, no callers yet.

No existing imports, no existing queries, no existing Celery tasks are modified.

### 5.3 Will This Affect Running Pipelines?

**No.** The `ChainOrchestrator` v3 is not yet wired into the Celery task pipeline. It will be wired in agent2. Until then, all changes are inert.

### 5.4 Database Migration: Additive-Only?

**Yes.** The migration only:
1. Creates a new table (`chain_runs`)
2. Creates 5 new indexes on that table

The `downgrade()` method drops indexes first (in correct order: dependent indexes last), then drops the table. No data is modified, no existing tables are altered.

### 5.5 Rollback Plan

1. **Migration rollback:** `alembic downgrade -1` — drops all indexes + the `chain_runs` table.
2. **Code rollback:** Delete the 3 new files. Revert the 2 modified imports.
3. **Data loss risk:** None. The table starts empty, and no code writes to it yet.
4. **FK cascade risk:** The table references `proyectos.id` with `ON DELETE CASCADE`. If a project is deleted, its chain runs are automatically deleted. This is correct behavior.

### 5.6 Forward Compatibility

- The `ChainRunModel` includes `TimestampMixin` (`creado_en`, `actualizado_en`) — consistent with all other models.
- `agent_runs` is stored as `JSONB` — flexible schema for future additions to `AgentRun` fields.
- `parent_chain_run_id` supports future branching without schema changes.
- The model class name `ChainRunModel` is deliberately distinct from the dataclass `ChainRun` to allow both to coexist in the codebase without name collision.

---

## 6. Post-Implementation Validation

### 6.1 Verify Migration Applied Correctly

```sql
-- Check table exists with correct columns
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'chain_runs'
ORDER BY ordinal_position;

-- Expected: 13 columns including id, project_id, chain_id, 
-- parent_chain_run_id, status, agent_runs, total_tokens, total_retries,
-- started_at, finished_at, created_by, creado_en, actualizado_en

-- Check indexes exist
SELECT indexname FROM pg_indexes WHERE tablename = 'chain_runs';
-- Expected: 5 indexes (pk + 4 custom + idx_chain_runs_created_at)

-- Check FK constraints
SELECT
    tc.constraint_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.referential_constraints rc
    ON tc.constraint_name = rc.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON rc.unique_constraint_name = ccu.constraint_name
WHERE tc.table_name = 'chain_runs' AND tc.constraint_type = 'FOREIGN KEY';
-- Expected: FK on project_id → proyectos.id (CASCADE)
--           FK on parent_chain_run_id → chain_runs.id (SET NULL)
```

### 6.2 Verify Dataclasses Are Importable

```bash
cd "/mnt/hdd/Program Files/Docker/gt/backend"
python -c "
from app.agents.chain_orchestrator import ChainState, AgentRun, ChainRun, ChainOrchestrator
from app.agents.tool_cache import ToolCache

# Test ChainState
s = ChainState(start_time=0.0, timeout_seconds=10.0)
print('ChainState.elapsed:', type(s.elapsed).__name__)  # float

# Test AgentRun
ar = AgentRun(
    agent_id='test', attempt_number=1, output={}, tokens_used=100,
    tool_calls_count=5, retry_count=0, orchestrator_action='proceed',
    started_at='2026-01-01T00:00:00Z', finished_at='2026-01-01T00:01:00Z'
)
print('AgentRun:', ar)

# Test ChainRun
cr = ChainRun(
    chain_id='test_chain', project_id='uuid', parent_chain_run_id=None,
    status='running', agent_runs=[], total_tokens=0, total_retries=0,
    started_at='2026-01-01T00:00:00Z', finished_at=None, created_by='system'
)
print('ChainRun:', cr)

# Test ToolCache
tc = ToolCache()
tc.set('search', {'q': 'test'}, {'results': [1, 2]})
assert tc.get('search', {'q': 'test'}) == {'results': [1, 2]}
assert tc.get('search', {'q': 'other'}) is None
tc.clear()
assert len(tc) == 0
print('ToolCache: OK')

print('All imports and basic tests PASSED')
"
```

Expected output:
```
ChainState.elapsed: float
AgentRun: AgentRun(agent_id='test', ...)
ChainRun: ChainRun(chain_id='test_chain', ...)
ToolCache: OK
All imports and basic tests PASSED
```

### 6.3 Unit-Test `decide()` — All 6 Branches

```python
# Save as: backend/tests/unit/test_chain_orchestrator.py
"""Test unitario de ChainOrchestrator.decide() — todas las ramas."""

import time
from dataclasses import dataclass

import pytest

from app.agents.chain_orchestrator import ChainOrchestrator, ChainState


@dataclass
class MockSelfEval:
    suggested_action: str
    retry_reason: str | None = "mock reason"


class MockAgentOutput:
    def __init__(self, action: str, reason: str | None = "mock reason"):
        self.self_eval = MockSelfEval(action, reason)


class TestChainOrchestratorDecide:
    """Test decidir() — 6 ramas + timeout + fallback."""

    @pytest.fixture
    def orchestrator(self):
        return ChainOrchestrator(max_retries=3)

    @pytest.fixture
    def fresh_state(self):
        return ChainState(start_time=time.monotonic(), timeout_seconds=600.0)

    def test_timeout_aborts_regardless_of_action(self, orchestrator):
        """Timeout → abort siempre, sin importar qué sugiera el agente."""
        state = ChainState(start_time=time.monotonic() - 9999, timeout_seconds=0.001)
        output = MockAgentOutput("proceed")
        action, reason = orchestrator.decide(output, 0, state)
        assert action == "abort"
        assert "time limit" in reason.lower()

    def test_proceed(self, orchestrator, fresh_state):
        """Agente dice proceed → proceed."""
        output = MockAgentOutput("proceed")
        action, reason = orchestrator.decide(output, 0, fresh_state)
        assert action == "proceed"
        assert reason is None

    def test_retry_within_limit(self, orchestrator, fresh_state):
        """Agente dice retry y estamos bajo el límite → retry."""
        output = MockAgentOutput("retry", "need more data")
        action, reason = orchestrator.decide(output, 2, fresh_state)  # 2 < 3
        assert action == "retry"
        assert reason == "need more data"

    def test_retry_exceeds_limit(self, orchestrator, fresh_state):
        """Agente dice retry pero ya alcanzamos max_retries → force_proceed."""
        output = MockAgentOutput("retry", "need more data")
        action, reason = orchestrator.decide(output, 3, fresh_state)  # 3 >= 3
        assert action == "force_proceed"
        assert "Max retries" in reason

    def test_escalate_to_hitl(self, orchestrator, fresh_state):
        """Agente pide HITL → pause_hitl."""
        output = MockAgentOutput("escalate_to_hitl", "ambiguous result")
        action, reason = orchestrator.decide(output, 0, fresh_state)
        assert action == "pause_hitl"
        assert reason == "ambiguous result"

    def test_skip(self, orchestrator, fresh_state):
        """Agente dice skip → skip."""
        output = MockAgentOutput("skip")
        action, reason = orchestrator.decide(output, 0, fresh_state)
        assert action == "skip"
        assert reason is None

    def test_abort(self, orchestrator, fresh_state):
        """Agente dice abort → abort."""
        output = MockAgentOutput("abort", "fatal error detected")
        action, reason = orchestrator.decide(output, 0, fresh_state)
        assert action == "abort"
        assert reason == "fatal error detected"

    def test_fallback_unknown_action(self, orchestrator, fresh_state):
        """Acción desconocida → fallback a proceed."""
        output = MockAgentOutput("nonexistent_action")
        action, reason = orchestrator.decide(output, 0, fresh_state)
        assert action == "proceed"
        assert reason is None

    def test_custom_max_retries(self, fresh_state):
        """max_retries configurable."""
        orch = ChainOrchestrator(max_retries=5)
        output = MockAgentOutput("retry", "need more data")
        action, reason = orch.decide(output, 4, fresh_state)  # 4 < 5
        assert action == "retry"
        action2, _ = orch.decide(output, 5, fresh_state)  # 5 >= 5
        assert action2 == "force_proceed"
```

**Run the tests:**
```bash
cd "/mnt/hdd/Program Files/Docker/gt/backend"
python -m pytest tests/unit/test_chain_orchestrator.py -v
```

Expected: **8 tests passing** (timeout, proceed, retry_within, retry_exceeds, hitl, skip, abort, fallback, custom_max_retries).

### 6.4 Verify Migration Can Be Applied + Reverted

```bash
cd "/mnt/hdd/Program Files/Docker/gt/backend"

# Generate migration (auto-generate, then review/customize)
alembic revision --autogenerate -m "chain_runs"

# Apply migration
alembic upgrade head

# Verify table exists
python -c "
from app.core.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chain_runs')\"))
    print('Table exists:', result.scalar())
"

# Rollback
alembic downgrade -1

# Verify table is gone
python -c "
from app.core.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chain_runs')\"))
    print('Table still exists:', result.scalar())
"
```

### 6.5 Verify Migration `env.py` Import

```bash
cd "/mnt/hdd/Program Files/Docker/gt/backend"
python -c "
from app.models.domain.chain_run import ChainRunModel
print('ChainRunModel imported successfully')
print('Table name:', ChainRunModel.__tablename__)
print('Columns:', [c.name for c in ChainRunModel.__table__.columns])
"
```

Expected output:
```
ChainRunModel imported successfully
Table name: chain_runs
Columns: ['id', 'project_id', 'chain_id', 'parent_chain_run_id', 'status', 
          'agent_runs', 'total_tokens', 'total_retries', 'started_at', 
          'finished_at', 'created_by', 'creado_en', 'actualizado_en']
```

---

## Appendix: Summary of All Changes

| # | Type | File | Action |
|---|------|------|--------|
| C1a | New | `backend/app/models/domain/chain_run.py` | Create `ChainRunModel` SQLAlchemy model |
| C1b | New | `backend/migrations/versions/NNN_chain_runs.py` | Create Alembic migration |
| C1c | Edit | `backend/migrations/env.py` line ~55 | Add `from app.models.domain.chain_run import ChainRunModel` |
| C4 | New | `backend/app/agents/tool_cache.py` | Create `ToolCache` class |
| C5+C6 | New | `backend/app/agents/chain_orchestrator.py` | Create `ChainState`, `AgentRun`, `ChainRun` dataclasses + `ChainOrchestrator.decide()` |
| - | Edit | `backend/app/agents/__init__.py` | Add exports for all new public symbols |

**Total: 3 new files, 2 files edited. 0 files deleted.**
