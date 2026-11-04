"""Prompt-caching invariants.

Fireworks caches an **exact prefix** of the request (see
https://docs.fireworks.ai/guides/prompt-caching). Two things must hold for a
batch of documents to reuse that cache:

1. The per-document text must not appear in the *system* prompt, otherwise
   every document invalidates the prefix from the first differing token.
2. All requests of the batch must carry the same ``x-session-affinity`` value,
   because the cache lives inside a single replica.

These tests assert both invariants without making a network call: the fast
worker's provider is replaced by a recorder that captures the kwargs of every
``chat()`` call.

The structural probe runs inside ``worker-fast`` because that is the only
container where ``llm_client`` resolves to ``workers/fast/llm_client.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.workflow.conftest import docker_compose_exec

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── In-container structural probe ──────────────────────────────────────

CACHE_PROBE = r"""
import types

import llm_client as fast

client = fast.LLMClient(api_key="sk-cache-probe")
client.is_mock = False

captured = []


class Recorder:
    is_mock = False
    timeout = 1

    def chat(self, **kwargs):
        captured.append(kwargs)
        return types.SimpleNamespace(
            content='{"punctuated_text": "ok", "changes_made": false}',
            reasoning_content="",
        )


client._provider = Recorder()

DOCS = [
    "<texto_crudo>\nEl PRIMER documento habla de sequias.\n</texto_crudo>",
    "<texto_crudo>\nEl SEGUNDO documento habla de lluvias.\n</texto_crudo>",
]

for body in DOCS:
    client.run_agent(
        "util_punctuator",
        variables={"raw_text": body},
        temperature=0.3,
        cache_key="project-affinity-key",
        tail_variables=("raw_text",),
        user_content=body,
    )

assert len(captured) == 2, captured

systems = [call["messages"][0]["content"] for call in captured]
users = [call["messages"][1]["content"] for call in captured]

# 1. Static prefix: instructions (+ schema) identical across documents.
assert systems[0] == systems[1], (
    "system prompt differs between documents; prompt caching cannot hit"
)

# 2. The document text lives only in the trailing user message.
for body, system, user in zip(DOCS, systems, users):
    assert body not in system, "document text leaked into the cached prefix"
    assert body in user, "document text missing from the user message"

# 3. Affinity: every request of the batch pins the same replica.
for call in captured:
    assert call.get("session_affinity") == "project-affinity-key", call

print("ok")
"""


def test_punctuator_prefix_is_static_and_affinity_is_set(docker):
    """The punctuator must separate static instructions from document text."""
    proc = docker_compose_exec("worker-fast", "python", "-c", CACHE_PROBE)
    assert proc.returncode == 0, (
        "prompt-caching probe failed for util_punctuator:\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1500]}"
    )
    assert "ok" in proc.stdout


ENTITY_CACHE_PROBE = r"""
import types

import llm_client as fast

client = fast.LLMClient(api_key="sk-cache-probe")
client.is_mock = False

captured = []


class Recorder:
    is_mock = False
    timeout = 1

    def chat(self, **kwargs):
        captured.append(kwargs)
        return types.SimpleNamespace(
            content='{"entities": [], "relations": []}',
            reasoning_content="",
        )


client._provider = Recorder()

SEGMENTS = [
    ("seg-1", "El PRIMER segmento habla de sequias y cultivos."),
    ("seg-2", "El SEGUNDO segmento habla de lluvias e inundaciones."),
]

for sid, body in SEGMENTS:
    client.run_agent(
        "util_entity_extraction",
        variables={"segment_text": body, "segment_id": sid},
        temperature=0.2,
        cache_key="project-affinity-key",
        tail_variables=("segment_text", "segment_id"),
        user_content=f"[SEGMENT]\n{body}\n\n[SEGMENT ID]\n{sid}",
    )

assert len(captured) == 2, captured

systems = [call["messages"][0]["content"] for call in captured]
users = [call["messages"][1]["content"] for call in captured]

# 1. Static prefix: instructions (+ schema) identical across segments.
assert systems[0] == systems[1], (
    "system prompt differs between segments; prompt caching cannot hit"
)

# 2. The segment text lives only in the trailing user message.
for (sid, body), system, user in zip(SEGMENTS, systems, users):
    assert body not in system, "segment text leaked into the cached prefix"
    assert sid not in system, "segment id leaked into the cached prefix"
    assert body in user, "segment text missing from the user message"
    assert sid in user, "segment id missing from the user message"

# 3. Affinity: every request of the batch pins the same replica.
for call in captured:
    assert call.get("session_affinity") == "project-affinity-key", call

print("ok")
"""


def test_entity_extraction_prefix_is_static_and_affinity_is_set(docker):
    """Entity extraction must keep segment text out of the cached prefix."""
    proc = docker_compose_exec("worker-fast", "python", "-c", ENTITY_CACHE_PROBE)
    assert proc.returncode == 0, (
        "prompt-caching probe failed for util_entity_extraction:\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1500]}"
    )
    assert "ok" in proc.stdout


PATTERN_CACHE_PROBE = r"""
import types

import llm_client as heavy

client = heavy.LLMClient(api_key="sk-cache-probe")
client.is_mock = False

captured = []


class Recorder:
    is_mock = False
    timeout = 1

    def chat(self, **kwargs):
        captured.append(kwargs)
        return types.SimpleNamespace(
            content=(
                '{"patterns": [], "incidents": [], '
                '"document_signals": {"core_pattern": "x", '
                '"tentative_concern": "y"}}'
            ),
            reasoning_content="",
        )


client._provider = Recorder()

DOCUMENTS = [
    ("primer.txt", "El PRIMER documento habla de sequias."),
    ("segundo.txt", "El SEGUNDO documento habla de lluvias."),
]

for name, body in DOCUMENTS:
    client.run_agent(
        "fa_document_pattern_extractor",
        variables={
            "segments_text": body,
            "document_name": name,
            "object_of_study": "adaptation",
            "operational_question": "how?",
        },
        cache_key="project-affinity-key",
        tail_variables=("segments_text", "document_name"),
        user_content=(
            f"[DOCUMENT]\nName: {name}\n\n"
            f"[ALL BASELINE SEGMENTS FROM THIS DOCUMENT]\n{body}"
        ),
    )

assert len(captured) == 2, captured

systems = [call["messages"][0]["content"] for call in captured]
users = [call["messages"][1]["content"] for call in captured]

# 1. Static prefix: instructions (+ schema) identical across documents.
assert systems[0] == systems[1], (
    "system prompt differs between documents; prompt caching cannot hit"
)

# 2. The document text and name live only in the trailing user message.
for (name, body), system, user in zip(DOCUMENTS, systems, users):
    assert body not in system, "document text leaked into the cached prefix"
    assert name not in system, "document name leaked into the cached prefix"
    assert body in user, "document text missing from the user message"
    assert name in user, "document name missing from the user message"

# 3. Affinity: every request of the batch pins the same replica.
for call in captured:
    assert call.get("session_affinity") == "project-affinity-key", call

print("ok")
"""


def test_pattern_extractor_prefix_is_static_and_affinity_is_set(docker):
    """Pattern extraction must keep document text out of the cached prefix."""
    proc = docker_compose_exec(
        "worker-heavy", "python", "-c", PATTERN_CACHE_PROBE, timeout=120
    )
    assert proc.returncode == 0, (
        "prompt-caching probe failed for fa_document_pattern_extractor:\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1500]}"
    )
    assert "ok" in proc.stdout


RELATION_TYPE_PROBE = r"""
import tasks

accepted = {
    "CAUSA",
    "CONDICION",
    "CONSECUENCIA",
    "OPOSICION",
    "COOCURRENCIA",
}
mapping = tasks.RELATION_TYPE_MAP

assert mapping["CAUSES"] == "CAUSA", mapping
assert set(mapping.values()) <= accepted, mapping
print("ok")
"""


def test_relation_type_map_is_db_compatible(docker):
    """Every mapped relation type must be accepted by the DB constraint."""
    proc = docker_compose_exec("worker-fast", "python", "-c", RELATION_TYPE_PROBE)
    assert proc.returncode == 0, (
        "RELATION_TYPE_MAP contains a value the DB rejects:\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1500]}"
    )
    assert "ok" in proc.stdout


HEADER_PROBE = r"""
import requests

from app.core.llm_client import LLMProvider

captured = {}


class FakeResponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"choices": [{"message": {"content": "hola"}}]}


def fake_post(url, json=None, headers=None, timeout=None):
    captured["headers"] = headers or {}
    return FakeResponse()


requests.post = fake_post
provider = LLMProvider(api_key="sk-header-probe")
provider.chat(
    model="pro",
    messages=[{"role": "user", "content": "hola"}],
    session_affinity="project-affinity-key",
)
headers = captured.get("headers", {})
assert headers.get("x-session-affinity") == "project-affinity-key", headers
assert headers.get("Authorization", "").startswith("Bearer "), headers
print("ok")
"""


def test_provider_sends_session_affinity_header(docker):
    """The affinity key must reach the wire as ``x-session-affinity``."""
    proc = docker_compose_exec("fastapi", "python", "-c", HEADER_PROBE)
    assert proc.returncode == 0, (
        "provider did not send x-session-affinity:\n"
        f"{proc.stdout.strip()}\n{proc.stderr.strip()[:1500]}"
    )
    assert "ok" in proc.stdout


# ── Source-level invariants (no container needed) ──────────────────────


def test_punctuator_prompt_has_no_inline_document_text():
    """``{raw_text}`` must not be interpolated into the system prompt."""
    prompt = (
        REPO_ROOT
        / "backend"
        / "app"
        / "prompts"
        / "agents"
        / "util_punctuator"
        / "prompt.md"
    ).read_text(encoding="utf-8")
    assert "{raw_text}" not in prompt, (
        "util_punctuator/prompt.md still embeds the document in the system "
        "prompt; move it to the user message so the prefix stays cacheable"
    )


def test_punctuate_task_forwards_cache_key():
    """The Celery task must accept and forward the batch affinity key."""
    source = (REPO_ROOT / "workers" / "fast" / "tasks.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    tasks = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    func = tasks.get("punctuate_text")
    assert func is not None, "punctuate_text not found"
    args = [a.arg for a in func.args.args]
    assert "cache_key" in args, "punctuate_text must accept cache_key"

    calls = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_agent"
    ]
    assert calls, "punctuate_text no longer calls llm.run_agent"
    keywords = {kw.arg for call in calls for kw in call.keywords}
    assert {"cache_key", "tail_variables", "user_content"} <= keywords, (
        "punctuate_text must pass cache_key/tail_variables/user_content to "
        f"run_agent; got {sorted(keywords)}"
    )


def test_punctuate_endpoint_sends_cache_key():
    """The API must derive the affinity key from the document's project."""
    source = (REPO_ROOT / "backend" / "app" / "api" / "v1" / "documents.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    handlers = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("punctuate_document", "process_document"):
        func = handlers.get(name)
        assert func is not None, f"{name} not found"
        send_tasks = [
            node
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "send_task"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "punctuate_text"
        ]
        assert send_tasks, f"{name} no longer dispatches punctuate_text"
        for call in send_tasks:
            kwargs = next(
                (kw.value for kw in call.keywords if kw.arg == "kwargs"),
                None,
            )
            assert isinstance(kwargs, ast.Dict), (
                f"{name}: send_task must pass kwargs as a dict literal"
            )
            keys = {k.value for k in kwargs.keys if isinstance(k, ast.Constant)}
            assert "cache_key" in keys, (
                f"{name}: punctuate_text dispatched without cache_key, so the "
                "batch will not be pinned to one replica"
            )


def test_glaser_classifier_pins_replica():
    """The Glaser classifier already sends static system + variable user."""
    source = (REPO_ROOT / "workers" / "heavy" / "glaser_classifier.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    func = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_step1_classify_xml"
        ),
        None,
    )
    assert func is not None, "_step1_classify_xml not found"
    calls = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "chat"
    ]
    assert any(kw.arg == "cache_key" for call in calls for kw in call.keywords), (
        "the Glaser classifier must forward cache_key to LLMClient.chat"
    )


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


def _run_agent_calls(func: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_agent"
    ]


def test_extract_graph_entities_forwards_cache_arguments():
    """Graph entity extraction must opt into the cached-prefix contract."""
    source = (REPO_ROOT / "workers" / "fast" / "tasks.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    func = _find_function(tree, "extract_graph_entities")
    calls = _run_agent_calls(func)
    assert calls, "extract_graph_entities no longer calls llm.run_agent"

    call = calls[0]
    agent_id = next(
        (kw.value for kw in call.keywords if kw.arg == "agent_id"),
        None,
    )
    assert isinstance(agent_id, ast.Constant), (
        "extract_graph_entities must pass a literal agent_id keyword"
    )
    assert agent_id.value == "util_entity_extraction", (
        f"unexpected agent id {agent_id.value!r}"
    )

    keywords = {kw.arg for kw in call.keywords}
    assert {"cache_key", "tail_variables", "user_content"} <= keywords, (
        "extract_graph_entities must pass cache_key/tail_variables/user_content "
        f"to run_agent; got {sorted(keywords)}"
    )


def test_extract_graph_entities_drops_nonexistent_agent_id():
    """The old, nonexistent agent id must not linger in the fast worker."""
    source = (REPO_ROOT / "workers" / "fast" / "tasks.py").read_text(encoding="utf-8")
    assert "util_graph_entity_extractor" not in source, (
        "workers/fast/tasks.py still references the nonexistent "
        "util_graph_entity_extractor agent"
    )


def test_extract_patterns_and_incidents_forwards_cache_arguments():
    """Pattern extraction must opt into the cached-prefix contract."""
    source = (REPO_ROOT / "workers" / "heavy" / "pattern_extractor.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    func = _find_function(tree, "extract_patterns_and_incidents")
    calls = _run_agent_calls(func)
    assert calls, "extract_patterns_and_incidents no longer calls llm.run_agent"

    call = calls[0]
    if call.args:
        assert isinstance(call.args[0], ast.Constant)
        assert call.args[0].value == "fa_document_pattern_extractor", (
            f"unexpected agent id {call.args[0].value!r}"
        )

    keywords = {kw.arg for kw in call.keywords}
    assert {"cache_key", "tail_variables", "user_content"} <= keywords, (
        "extract_patterns_and_incidents must pass "
        f"cache_key/tail_variables/user_content to run_agent; got {sorted(keywords)}"
    )


def test_entity_extraction_prompt_has_no_inline_segment_text():
    """``{segment_text}``/``{segment_id}`` must not sit in the system prompt."""
    prompt = (
        REPO_ROOT
        / "backend"
        / "app"
        / "prompts"
        / "agents"
        / "util_entity_extraction"
        / "prompt.md"
    ).read_text(encoding="utf-8")
    assert "{segment_text}" not in prompt, (
        "util_entity_extraction/prompt.md still embeds the segment in the "
        "system prompt; move it to the user message so the prefix stays "
        "cacheable"
    )
    assert "{segment_id}" not in prompt, (
        "util_entity_extraction/prompt.md still embeds the segment id in the "
        "system prompt"
    )


def test_pattern_extractor_prompt_has_no_inline_document_text():
    """``{segments_text}``/``{document_name}`` must not sit in the system prompt."""
    prompt = (
        REPO_ROOT
        / "backend"
        / "app"
        / "prompts"
        / "agents"
        / "fa_document_pattern_extractor"
        / "prompt.md"
    ).read_text(encoding="utf-8")
    assert "{segments_text}" not in prompt, (
        "fa_document_pattern_extractor/prompt.md still embeds the segments in "
        "the system prompt; move them to the user message so the prefix stays "
        "cacheable"
    )
    assert "{document_name}" not in prompt, (
        "fa_document_pattern_extractor/prompt.md still embeds the document "
        "name in the system prompt"
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        "workers/fast/llm_client.py",
        "workers/heavy/llm_client.py",
    ],
)
def test_workers_expose_cache_tail_marker(relative_path: str):
    """Both worker adapters must expose the shared cache-tail marker."""
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "CACHE_TAIL_MARKER" in source
    assert "session_affinity=" in source
