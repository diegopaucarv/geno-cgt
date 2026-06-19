"""Logs populated prompts and LLM responses to Redis for frontend consumption."""

import json
import logging
import os
import time

logger = logging.getLogger(__name__)


def log_prompt_call(
    agent_id: str, project_id: str, populated_prompt: str, schema: dict | None = None
):
    """Log the populated prompt BEFORE sending to LLM."""
    try:
        import redis as _r

        r = _r.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        entry = {
            "ts": time.time(),
            "type": "prompt_sent",
            "agent_id": agent_id,
            "prompt": populated_prompt[:8000],  # truncate for storage
            "schema": json.dumps(schema, ensure_ascii=False)[:2000] if schema else None,
        }
        r.rpush(f"agent_logs:{project_id}", json.dumps(entry, ensure_ascii=False))
        r.expire(f"agent_logs:{project_id}", 86400)
    except Exception:
        pass


def log_prompt_response(
    agent_id: str, project_id: str, response: dict, tokens: int = 0
):
    """Log the LLM response AFTER receiving it."""
    try:
        import redis as _r

        r = _r.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        entry = {
            "ts": time.time(),
            "type": "prompt_response",
            "agent_id": agent_id,
            "response": json.dumps(response, ensure_ascii=False)[:8000],
            "tokens": tokens,
        }
        r.rpush(f"agent_logs:{project_id}", json.dumps(entry, ensure_ascii=False))
        r.expire(f"agent_logs:{project_id}", 86400)
    except Exception:
        pass
