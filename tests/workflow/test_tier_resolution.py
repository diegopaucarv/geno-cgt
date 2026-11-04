"""Tier-resolution invariants for the worker prompt adapters.

The prompt files under ``backend/app/prompts/agents`` declare their model tier
either with ``tier:`` or with the legacy ``model_profile:`` key, and the values
are spelled in lowercase (``pro``/``flash``). Both worker adapters must
normalise those values to the canonical ``PRO``/``FLASH`` tiers instead of
silently defaulting every agent to PRO.

Like ``test_prompt_caching.py``, these tests never import the worker modules:
they read the adapter sources with ``Path.read_text``/``ast`` and exercise the
extracted ``resolve_model_tier`` function directly.
"""

from __future__ import annotations

import ast
import logging
import re
from functools import lru_cache
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "prompts" / "agents"
WORKER_ADAPTERS = (
    REPO_ROOT / "workers" / "fast" / "llm_client.py",
    REPO_ROOT / "workers" / "heavy" / "llm_client.py",
)
PROMPT_PATHS = sorted(PROMPTS_DIR.glob("*/prompt.md"))
VALID_TIERS = {"PRO", "FLASH"}

# The exact fallback both adapters used before ``resolve_model_tier`` existed.
OLD_INLINE_PATTERN = 'declared_tier if declared_tier in ("PRO", "FLASH") else "PRO"'

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
_METADATA_LINE_RE = re.compile(r"^(tier|model_profile)\s*:\s*(.+?)\s*$", re.MULTILINE)
_LEGACY_METADATA_LINE_RE = re.compile(
    r"^--\s*(tier|model_profile)\s*:\s*(.+?)\s*$", re.MULTILINE
)


# ── Prompt metadata parsing ────────────────────────────────────────────


def _parse_prompt_metadata(path: Path) -> dict[str, str]:
    """Collect ``tier``/``model_profile`` from frontmatter or legacy lines."""
    # The adapters strip the raw prompt before detecting the format; a few
    # prompt files start with stray indentation before the opening ``---``.
    text = path.read_text(encoding="utf-8").strip()
    metadata: dict[str, str] = {}

    frontmatter = _FRONTMATTER_RE.match(text)
    if frontmatter:
        body = frontmatter.group(1)
        for match in _METADATA_LINE_RE.finditer(body):
            metadata[match.group(1)] = match.group(2).strip().strip("'\"")

    for match in _LEGACY_METADATA_LINE_RE.finditer(text):
        metadata[match.group(1)] = match.group(2).strip().strip("'\"")

    return metadata


def _declared_tier(metadata: dict[str, str]) -> str:
    """Normalised declared tier, without applying the PRO fallback."""
    raw = metadata.get("tier") or metadata.get("model_profile") or ""
    return raw.strip().upper()


# ── Loading the real helper without importing the worker module ─────────


@lru_cache(maxsize=None)
def _extract_resolver(path: Path):
    """Exec just ``resolve_model_tier`` from an adapter source file.

    Importing the adapter would pull in ``app.core.*`` (and therefore the
    container runtime), so the function AST is compiled in isolation with a
    stub logger instead.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    func = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "resolve_model_tier"
        ),
        None,
    )
    assert func is not None, f"{path} does not define resolve_model_tier"

    module = ast.Module(body=[func], type_ignores=[])
    namespace: dict[str, object] = {
        "ModelTier": str,
        "logger": logging.getLogger("tier-resolution-test"),
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["resolve_model_tier"]


@pytest.fixture(
    params=WORKER_ADAPTERS, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}"
)
def resolver(request: pytest.FixtureRequest):
    return _extract_resolver(request.param)


# ── Prompt files ──────────────────────────────────────────────────────


def test_prompt_directory_is_not_empty():
    assert PROMPT_PATHS, f"no prompt files found under {PROMPTS_DIR}"


@pytest.mark.parametrize("prompt_path", PROMPT_PATHS, ids=lambda p: p.parent.name)
def test_every_prompt_resolves_to_a_valid_tier(prompt_path: Path):
    """Every agent prompt must resolve to PRO or FLASH, never a fallback miss."""
    metadata = _parse_prompt_metadata(prompt_path)
    assert "tier" in metadata or "model_profile" in metadata, (
        f"{prompt_path} declares neither tier nor model_profile"
    )

    fast_resolver = _extract_resolver(WORKER_ADAPTERS[0])
    resolved = fast_resolver(metadata, prompt_path.parent.name)
    assert resolved in VALID_TIERS, f"{prompt_path} resolved to {resolved!r}"


def test_at_least_one_prompt_declares_flash():
    flash_prompts = [
        path.parent.name
        for path in PROMPT_PATHS
        if _declared_tier(_parse_prompt_metadata(path)) == "FLASH"
    ]
    assert flash_prompts, (
        "no prompt declares a FLASH tier; the parametrised test above would "
        "pass trivially"
    )


@pytest.mark.parametrize("agent_id", ["b2a", "util_entity_extraction"])
def test_flash_agents_resolve_to_flash(agent_id: str):
    """Regression canary: these agents must not silently fall back to PRO."""
    prompt_path = PROMPTS_DIR / agent_id / "prompt.md"
    metadata = _parse_prompt_metadata(prompt_path)

    fast_resolver = _extract_resolver(WORKER_ADAPTERS[0])
    assert fast_resolver(metadata, agent_id) == "FLASH", (
        f"{agent_id} declares flash but does not resolve to FLASH"
    )


# ── Adapter source invariants ───────────────────────────────────────────


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    func = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        ),
        None,
    )
    assert func is not None, f"{name} not found"
    return func


@pytest.mark.parametrize(
    "adapter", WORKER_ADAPTERS, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}"
)
def test_adapter_uses_resolve_model_tier(adapter: Path):
    source = adapter.read_text(encoding="utf-8")

    assert "def resolve_model_tier(" in source, (
        f"{adapter} does not define resolve_model_tier"
    )
    assert OLD_INLINE_PATTERN not in source, (
        f"{adapter} still contains the old inline tier fallback"
    )
    assert "declared_tier" not in source, (
        f"{adapter} still references the removed declared_tier variable"
    )

    tree = ast.parse(source)
    run_agent = _find_function(tree, "run_agent")
    resolver_calls = [
        node
        for node in ast.walk(run_agent)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_model_tier"
    ]
    assert resolver_calls, f"{adapter}'s run_agent does not call resolve_model_tier"

    assert 'resolve_model_tier(parsed["metadata"], agent_id)' in source, (
        f"{adapter} must pass the parsed metadata and agent id to the helper"
    )


@pytest.mark.parametrize(
    "adapter", WORKER_ADAPTERS, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}"
)
def test_legacy_parser_captures_model_profile(adapter: Path):
    """The legacy ``-- key:`` parser must expose both tier keys."""
    source = adapter.read_text(encoding="utf-8")
    assert '"-- tier:"' in source
    assert '"-- model_profile:"' in source


# ── Resolution semantics ────────────────────────────────────────────────


def test_tier_wins_over_model_profile(resolver):
    assert resolver({"tier": "pro", "model_profile": "flash"}) == "PRO"
    assert resolver({"tier": "flash", "model_profile": "pro"}) == "FLASH"


def test_model_profile_is_used_when_tier_is_absent(resolver):
    assert resolver({"model_profile": "flash"}) == "FLASH"
    assert resolver({"model_profile": "pro"}) == "PRO"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pro", "PRO"),
        ("PRO", "PRO"),
        ("  Pro  ", "PRO"),
        ("flash", "FLASH"),
        ("FLASH", "FLASH"),
        ("  Flash  ", "FLASH"),
    ],
)
def test_tier_case_and_whitespace_are_normalised(resolver, raw: str, expected: str):
    assert resolver({"tier": raw}) == expected


def test_unknown_tier_defaults_to_pro_and_warns(resolver, caplog):
    with caplog.at_level(logging.WARNING):
        assert resolver({"tier": "turbo"}, agent_id="agent-x") == "PRO"

    assert "agent-x" in caplog.text
    assert "turbo" in caplog.text


def test_missing_tier_defaults_to_pro_and_warns(resolver, caplog):
    with caplog.at_level(logging.WARNING):
        assert resolver({}, agent_id="agent-y") == "PRO"

    assert "agent-y" in caplog.text
