"""Chain Runs endpoints — query execution history from the ChainOrchestrator v3."""

import logging
from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["chain_runs"])

logger = logging.getLogger(__name__)


# ── Response schemas ─────────────────────────────────────────────────


class AgentRunResponse(BaseModel):
    agent_id: str
    attempt_number: int
    output: dict = Field(default_factory=dict)
    tokens_used: int = 0
    tool_calls_count: int = 0
    retry_count: int = 0
    orchestrator_action: str = "proceed"
    started_at: str | None = None
    finished_at: str | None = None


class ChainRunResponse(BaseModel):
    id: str
    project_id: str
    chain_id: str
    parent_chain_run_id: str | None = None
    status: str
    agent_runs: list[AgentRunResponse] | None = None
    total_tokens: int = 0
    total_retries: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    created_by: str = "system"
    created_at: str | None = None


# ── Endpoint ─────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/chain-runs",
    response_model=list[ChainRunResponse],
)
async def get_chain_runs(
    project_id: UUID,
    chain_id: str | None = Query(
        None,
        description="Filter by chain identifier (e.g. 'open_coding_main')",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    include_agent_runs: bool = Query(
        True,
        description="Whether to include the agent_runs JSONB array",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Query chain execution history persisted by the ChainOrchestrator v3.

    Returns a list of ChainRun records ordered by created_at DESC.
    The `agent_runs` field can be omitted for lighter payloads by setting
    `include_agent_runs=false`.
    """
    # Build the SELECT clause: optionally omit the agent_runs JSONB column
    if include_agent_runs:
        select_cols = (
            "id, project_id, chain_id, parent_chain_run_id, status, "
            "agent_runs, total_tokens, total_retries, started_at, "
            "finished_at, created_by, created_at"
        )
    else:
        select_cols = (
            "id, project_id, chain_id, parent_chain_run_id, status, "
            "NULL::jsonb AS agent_runs, total_tokens, total_retries, started_at, "
            "finished_at, created_by, created_at"
        )

    # Build WHERE clause
    where_clauses = ["project_id = :pid"]
    params: dict = {"pid": project_id, "limit": limit}

    if chain_id:
        where_clauses.append("chain_id = :chain_id")
        params["chain_id"] = chain_id

    where_sql = " AND ".join(where_clauses)

    query = text(
        f"SELECT {select_cols} FROM chain_runs "
        f"WHERE {where_sql} "
        f"ORDER BY created_at DESC "
        f"LIMIT :limit"
    )

    try:
        result = await db.execute(query, params)
        rows = result.fetchall()
    except Exception as e:
        # If the chain_runs table doesn't exist yet, return empty list
        # rather than 500 — graceful degradation
        logger.warning(f"chain_runs query failed (table may not exist yet): {e}")
        return []

    # Map rows to response models
    chain_runs: list[ChainRunResponse] = []
    for row in rows:
        # row is a RowProxy; access by index or ._mapping
        row_map = row._mapping

        agent_runs_raw = row_map.get("agent_runs")
        agent_runs_parsed: list[AgentRunResponse] | None = None

        if include_agent_runs and agent_runs_raw is not None:
            # agent_runs_raw is a list of dicts from JSONB (or possibly a string)
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
                        agent_runs_parsed.append(
                            AgentRunResponse(
                                agent_id=ar.get("agent_id", ""),
                                attempt_number=ar.get("attempt_number", 1),
                                output=ar.get("output", {}),
                                tokens_used=ar.get("tokens_used", 0),
                                tool_calls_count=ar.get("tool_calls_count", 0),
                                retry_count=ar.get("retry_count", 0),
                                orchestrator_action=ar.get(
                                    "orchestrator_action", "proceed"
                                ),
                                started_at=ar.get("started_at"),
                                finished_at=ar.get("finished_at"),
                            )
                        )

        chain_runs.append(
            ChainRunResponse(
                id=str(row_map["id"]),
                project_id=str(row_map["project_id"]),
                chain_id=str(row_map["chain_id"]),
                parent_chain_run_id=str(row_map["parent_chain_run_id"])
                if row_map.get("parent_chain_run_id")
                else None,
                status=str(row_map["status"]),
                agent_runs=agent_runs_parsed,
                total_tokens=int(row_map.get("total_tokens") or 0),
                total_retries=int(row_map.get("total_retries") or 0),
                started_at=str(row_map["started_at"])
                if row_map.get("started_at")
                else None,
                finished_at=str(row_map["finished_at"])
                if row_map.get("finished_at")
                else None,
                created_by=str(row_map.get("created_by", "system")),
                created_at=str(row_map["created_at"])
                if row_map.get("created_at")
                else None,
            )
        )

    return chain_runs
