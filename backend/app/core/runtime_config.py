"""
Runtime configuration store.

Priority: env var > runtime.json > hardcoded default.

Reads a JSON file that can be updated at runtime via the /api/v1/config endpoint.
This allows the frontend config panel to persist changes without touching .env or code.

Usage:
    from app.core.runtime_config import get_runtime_config, update_runtime_config
    cfg = get_runtime_config()
    model_pro = cfg.get("MODEL_PRO", "deepseek-ai/DeepSeek-V4-Pro")
"""

import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

# Where the runtime overrides live (mounted as volume in docker-compose)
RUNTIME_CONFIG_PATH = os.getenv(
    "RUNTIME_CONFIG_PATH",
    "/app/config/runtime.json",
)

_lock = Lock()
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0


def _ensure_dir() -> None:
    Path(RUNTIME_CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_runtime_config() -> dict[str, Any]:
    """Returns the current runtime config dict. Cached until file changes."""
    global _cache, _cache_mtime

    try:
        mtime = os.path.getmtime(RUNTIME_CONFIG_PATH)
    except OSError:
        mtime = 0

    if _cache is not None and mtime == _cache_mtime:
        return _cache

    with _lock:
        try:
            with open(RUNTIME_CONFIG_PATH) as f:
                _cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _cache = {}
        _cache_mtime = (
            os.path.getmtime(RUNTIME_CONFIG_PATH)
            if os.path.exists(RUNTIME_CONFIG_PATH)
            else 0
        )
        return _cache


def update_runtime_config(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates into runtime.json, return the full new config."""
    _ensure_dir()
    with _lock:
        current = {}
        try:
            with open(RUNTIME_CONFIG_PATH) as f:
                current = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        current.update(updates)

        # Remove null values (allow clearing overrides)
        current = {k: v for k, v in current.items() if v is not None}

        with open(RUNTIME_CONFIG_PATH, "w") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

        global _cache, _cache_mtime
        _cache = current
        _cache_mtime = os.path.getmtime(RUNTIME_CONFIG_PATH)

        logger.info("Runtime config updated: %s", list(updates.keys()))
        return current


def get_config_value(key: str, env_var: str | None = None, default: Any = None) -> Any:
    """
    Resolve a config value with priority: env var > runtime.json > default.

    Args:
        key: Key in runtime.json
        env_var: Environment variable name (if different from key)
        default: Hardcoded fallback
    """
    env_name = env_var or key
    env_val = os.getenv(env_name)
    if env_val is not None:
        return env_val

    runtime = get_runtime_config()
    if key in runtime:
        return runtime[key]

    return default
