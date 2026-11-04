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

from tests.workflow.conftest import docker_compose_exec

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
