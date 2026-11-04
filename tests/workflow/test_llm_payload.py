"""Payload-shape regression for the shared LLM client.

Why this test exists
--------------------
The punctuator silently degraded to "mock" (and therefore returned the input
unchanged) because every request carried **both** ``repetition_penalty`` and
``frequency_penalty``.  The provider rejects that combination with HTTP 400:

    Validation: repetition_penalty cannot be combined with
    frequency_penalty or presence_penalty

The worker logged ``LLM call failed ... Mock fallback`` and stored the raw text,
so the UI showed a "preprocessed" document identical to the original.

The check runs *inside* the fastapi container because the module needs the
backend's runtime dependencies (pydantic, requests, the config layer), which are
not installed on the host.  It asserts on ``build_payload`` only: no network
call, no credential needed.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.workflow.conftest import docker_compose_exec

REPO_ROOT = Path(__file__).resolve().parents[2]

PAYLOAD_PROBE = r"""
from app.core.llm_client import LLMProvider

provider = LLMProvider(api_key="sk-regression-probe")
messages = [{"role": "user", "content": "hola"}]

for tier in ("pro", "flash"):
    payload = provider.build_payload(model=tier, messages=messages)
    has_rep = "repetition_penalty" in payload
    has_freq = "frequency_penalty" in payload
    has_pres = "presence_penalty" in payload
    if (has_rep and has_freq) or (has_rep and has_pres):
        raise SystemExit(
            f"tier={tier} sends incompatible penalties: "
            f"repetition_penalty={payload.get('repetition_penalty')!r} "
            f"frequency_penalty={payload.get('frequency_penalty')!r} "
            f"presence_penalty={payload.get('presence_penalty')!r}"
        )
    if payload["temperature"] < 0:
        raise SystemExit(f"tier={tier} has a negative temperature")

print("ok")
"""


def test_build_payload_does_not_combine_penalties(docker):
    """No tier may send repetition_penalty alongside frequency/presence."""
    # The probe loops over both pro and flash tiers internally.
    proc = docker_compose_exec("fastapi", "python", "-c", PAYLOAD_PROBE)
    assert proc.returncode == 0, (
        "build_payload produces a request the provider rejects (HTTP 400):\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:800]}"
    )
    assert "ok" in proc.stdout


# ── Structured-output wire format ──────────────────────────────────────
# Fireworks rejects a bare JSON Schema in ``response_format`` with HTTP 400:
#
#     Invalid json_schema format: ... type Extra inputs are not permitted
#
# ``json_schema`` must be the OpenAI-style {"name", "schema"} wrapper, not a
# schema itself. Every heavy-worker agent call with a schema failed on this and
# silently fell back to mock (pattern extraction returned 0 patterns).
SCHEMA_PROBE_BODY = r"""
provider = LLMProvider(api_key="sk-schema-probe")
messages = [{"role": "user", "content": "hola"}]
schema = {
    "type": "object",
    "properties": {"a": {"type": "string"}},
    "required": ["a"],
}

# 1. A bare schema must be wrapped as {"name", "schema"}.
payload = provider.build_payload(model="pro", messages=messages, schema=schema)
rf = payload["response_format"]
assert set(rf) == {"type", "json_schema"}, rf
assert rf["type"] == "json_schema", rf
wrapper = rf["json_schema"]
assert set(wrapper) == {"name", "schema"}, wrapper
name = wrapper["name"]
assert isinstance(name, str) and name, name
assert wrapper["schema"] == schema, wrapper
# The wrapper must not itself look like a JSON Schema.
for key in ("type", "properties", "required"):
    assert key not in wrapper, (key, wrapper)

# 2. A wrapper input preserves its explicit name.
payload = provider.build_payload(
    model="pro",
    messages=messages,
    schema={"name": "my_agent", "schema": schema},
)
wrapper = payload["response_format"]["json_schema"]
assert set(wrapper) == {"name", "schema"}, wrapper
assert wrapper["name"] == "my_agent", wrapper
assert wrapper["schema"] == schema, wrapper

# 3. json_object mode must stay a plain {"type": "json_object"}.
payload = provider.build_payload(
    model="pro",
    messages=messages,
    schema=schema,
    schema_mode="json_object",
)
assert payload["response_format"] == {"type": "json_object"}, payload

print("ok")
"""


def _schema_probe(module: str) -> str:
    return f"from {module} import LLMProvider\n" + SCHEMA_PROBE_BODY


def test_build_payload_wraps_json_schema(docker):
    """``json_schema`` must be a named object, never a bare schema."""
    proc = docker_compose_exec(
        "fastapi", "python", "-c", _schema_probe("app.core.llm_client")
    )
    assert proc.returncode == 0, (
        "build_payload emits a response_format Fireworks rejects (HTTP 400):\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1200]}"
    )
    assert "ok" in proc.stdout


def test_heavy_worker_build_payload_wraps_json_schema(docker):
    """The provider instance the heavy worker uses has the same wire contract."""
    proc = docker_compose_exec(
        "worker-heavy", "python", "-c", _schema_probe("backend.app.core.llm_client")
    )
    assert proc.returncode == 0, (
        "heavy worker build_payload emits a response_format Fireworks rejects "
        f"(HTTP 400):\n{proc.stdout.strip()}\n{proc.stderr.strip()[:1200]}"
    )
    assert "ok" in proc.stdout


# ── Source-level invariants (no container needed) ──────────────────────

ADAPTER = REPO_ROOT / "backend" / "app" / "core" / "llm_client_adapter.py"


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


def test_adapter_forwards_schema_name():
    """The adapter must surface the wrapper name to ``self._provider.chat``."""
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))

    split = _find_function(tree, "_split_response_format")
    returns = [node for node in ast.walk(split) if isinstance(node, ast.Return)]
    assert returns, "_split_response_format has no return statements"
    for ret in returns:
        assert isinstance(ret.value, ast.Tuple), ast.dump(ret)
        assert len(ret.value.elts) == 3, (
            "_split_response_format must return (mode, schema, name); got "
            f"{len(ret.value.elts)} value(s)"
        )

    annotation = split.returns
    assert isinstance(annotation, ast.Subscript), (
        "_split_response_format must annotate its 3-tuple return"
    )
    assert isinstance(annotation.slice, ast.Tuple), ast.dump(annotation)
    assert len(annotation.slice.elts) == 3, ast.dump(annotation)

    cls = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "TogetherLLM"
        ),
        None,
    )
    assert cls is not None, "TogetherLLM not found"
    chat = next(
        (
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "chat"
        ),
        None,
    )
    assert chat is not None, "TogetherLLM.chat not found"

    # The unpacking must keep the third value (the name) in scope.
    split_calls = [
        node
        for node in ast.walk(chat)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "_split_response_format"
    ]
    assert split_calls, "TogetherLLM.chat no longer calls _split_response_format"
    target = split_calls[0].targets[0]
    assert isinstance(target, ast.Tuple) and len(target.elts) == 3, ast.dump(target)

    provider_calls = [
        node
        for node in ast.walk(chat)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "chat"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_provider"
    ]
    assert provider_calls, "TogetherLLM.chat no longer calls self._provider.chat"
    assert any(
        kw.arg == "schema_name" for call in provider_calls for kw in call.keywords
    ), "TogetherLLM.chat must pass schema_name= to self._provider.chat"
