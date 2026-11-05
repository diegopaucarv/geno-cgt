"""
Unified LLM provider — the ONLY module that talks to the inference API.

Single source of truth for every LLM call in the system. All three
services (FastAPI backend, worker-heavy, worker-fast) import from here;
they keep their own thin adapters so that call sites did not have to change.

Design
──────
    LLMProvider        wire protocol: payload build → HTTP → normalisation
    LLMResponse        canonical result, provider-agnostic
    TierSettings       per-tier sampling knobs, resolved from config

Provider
────────
Fireworks AI, OpenAI-compatible surface:
    POST https://api.fireworks.ai/inference/v1/chat/completions

Both request shapes from the provider docs are supported:
    - ``content`` as a plain string (text-only)
    - ``content`` as a list of blocks (``{"type": "text"}`` /
      ``{"type": "image_url"}``) for multimodal prompts

Schema enforcement
──────────────────
``schema=`` is enforced, not advisory. Two wire formats:

    json_schema  {"type": "json_schema",
                  "json_schema": {"name": ..., "schema": <schema>}}
    json_object  {"type": "json_object"}

Fireworks requires the OpenAI-style wrapper: the JSON Schema must be nested
under ``json_schema`` together with a ``name``. Sending the bare schema in
that slot is rejected with ``Invalid json_schema format`` (HTTP 400).
``_schema_parts`` accepts either shape on input and ``build_payload`` always
emits the wrapped one.

Credentials
───────────
Exactly one variable: ``LLM_API_KEY``. Resolved through ``get_config_value``
so it follows the same env > runtime.json > default chain as everything else.
There is intentionally no per-provider key.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.llm_config import (
    MODEL_REGISTRY,
    TIER_DEFAULT_MODEL,
    ModelEndpoint,
    get_model_for_prompt,
)
from app.core.runtime_config import get_config_value

logger = logging.getLogger(__name__)

# ── Provider endpoint (env-overridable for self-hosted / proxied gateways) ──

DEFAULT_API_BASE = "https://api.fireworks.ai/inference/v1"
REQUEST_TIMEOUT_S = float(get_config_value("LLM_TIMEOUT_S", default="600"))

# Config keys that hold sampling knobs per tier.
_TIER_CONFIG_KEYS = (
    "MAX_TOKENS",
    "TEMPERATURE",
    "REPETITION_PENALTY",
    "FREQUENCY_PENALTY",
    "TOP_P",
)

# Answer text that must never be mistaken for a real completion.
_MOCK_ANSWER = '{"next_step": "final_report"}'


class LLMProviderError(RuntimeError):
    """Raised when the inference API fails in a way the caller must see."""


@dataclass(frozen=True)
class LLMResponse:
    """Canonical, provider-agnostic completion result."""

    content: str
    model: str
    tier: str
    reasoning_content: str = ""
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_result(self, **extra: Any) -> dict[str, Any]:
        """Backend ``chat()`` return contract (TogetherLLM-compatible)."""
        result: dict[str, Any] = {
            "content": self.content,
            "model": self.model,
            "tier": self.tier,
            "usage": self.usage or None,
            "finish_reason": self.finish_reason,
        }
        if self.reasoning_content:
            result["reasoning_content"] = self.reasoning_content
        result.update(extra)
        return result


@dataclass(frozen=True)
class TierSettings:
    """Sampling knobs for one tier, read from config at call time."""

    max_tokens: int
    temperature: float
    repetition_penalty: float
    frequency_penalty: float
    top_p: float

    @classmethod
    def for_tier(cls, tier: str) -> "TierSettings":
        """Resolve settings for ``pro``/``flash`` (case-insensitive)."""
        upper = (tier or "pro").upper()
        values: dict[str, float] = {}
        # Defaults mirror the historical per-worker tables so behaviour is stable.
        # ``FREQUENCY_PENALTY`` stays neutral on both tiers: reasoning models
        # (DeepSeek V4, Nemotron) degenerate when it is applied — the model
        # avoids repeating tokens by emitting whitespace, burning the output
        # budget until ``finish_reason=length`` returns empty ``content``.
        # ``REPETITION_PENALTY`` covers the same ground without that failure.
        fallbacks = {
            "MAX_TOKENS": "8192" if upper == "PRO" else "4096",
            "TEMPERATURE": "0.3" if upper == "PRO" else "0.1",
            "REPETITION_PENALTY": "1.0" if upper == "PRO" else "1.1",
            "FREQUENCY_PENALTY": "0.0",
            "TOP_P": "1.0" if upper == "PRO" else "0.9",
        }
        for knob in _TIER_CONFIG_KEYS:
            key = f"MODEL_{upper}_{knob}"
            raw = get_config_value(key, default=fallbacks[knob])
            try:
                values[knob] = float(raw)
            except (TypeError, ValueError):
                values[knob] = float(fallbacks[knob])
        return cls(
            max_tokens=int(values["MAX_TOKENS"]),
            temperature=values["TEMPERATURE"],
            repetition_penalty=values["REPETITION_PENALTY"],
            frequency_penalty=values["FREQUENCY_PENALTY"],
            top_p=values["TOP_P"],
        )


def resolve_api_key(api_key: str | None = None) -> str:
    """The one and only LLM credential."""
    return (
        api_key
        or get_config_value("LLM_API_KEY", default=os.getenv("LLM_API_KEY", ""))
        or ""
    ).strip()


def api_base_url() -> str:
    """Base URL of the OpenAI-compatible inference API."""
    base = (
        get_config_value("LLM_API_BASE", default=DEFAULT_API_BASE) or DEFAULT_API_BASE
    )
    return base.rstrip("/")


def is_placeholder_key(key: str) -> bool:
    """True when the configured key cannot authenticate a real request."""
    k = (key or "").strip()
    return (
        not k
        or k.startswith("${")
        or k.startswith("http")  # a URL where a key belongs
        or k in {"changeme", "CHANGEME", "your-api-key", "sk-xxx"}
    )


def is_mock_enabled(api_key: str | None = None) -> bool:
    """Mock mode is on when no usable credential is configured."""
    return is_placeholder_key(resolve_api_key(api_key))


def tier_of(model: Any) -> str:
    """Resolve the tier string for a model reference (``pro``/``flash``)."""
    if isinstance(model, ModelEndpoint):
        return model.tier
    if model is None:
        return "pro"
    ref = str(model)
    lowered = ref.lower()
    if lowered in ("pro", "flash"):
        return lowered
    if ref in MODEL_REGISTRY:
        return MODEL_REGISTRY[ref].tier
    if lowered in TIER_DEFAULT_MODEL:
        return lowered
    # A raw provider model id: infer from the registry it matches, else PRO.
    for endpoint in MODEL_REGISTRY.values():
        if endpoint.model_id == ref:
            return endpoint.tier
    return "pro"


def model_id_of(model: Any) -> str:
    """Resolve a provider model id / registry key / endpoint to a model id."""
    if isinstance(model, ModelEndpoint):
        return model.model_id
    if model is None:
        return MODEL_REGISTRY[TIER_DEFAULT_MODEL["pro"]].model_id
    ref = str(model)
    if ref in MODEL_REGISTRY:
        return MODEL_REGISTRY[ref].model_id
    lowered = ref.lower()
    if lowered in TIER_DEFAULT_MODEL:
        return MODEL_REGISTRY[TIER_DEFAULT_MODEL[lowered]].model_id
    # Raw id (e.g. "accounts/fireworks/models/...") — use verbatim.
    return ref


def resolve_endpoint(model: Any) -> ModelEndpoint:
    """Backwards-compatible resolver used by the backend adapter."""
    if isinstance(model, ModelEndpoint):
        return model
    if str(model) in MODEL_REGISTRY:
        return MODEL_REGISTRY[str(model)]
    tier = tier_of(model)
    return MODEL_REGISTRY[TIER_DEFAULT_MODEL[tier]]


def _schema_parts(schema: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(schema_obj, name)`` from a bare JSON Schema or a wrapper."""
    if not schema or not isinstance(schema, dict):
        return None, None
    # {"name": ..., "schema": {...}} or {"strict": ..., "schema": {...}}
    if "schema" in schema and isinstance(schema["schema"], dict):
        return schema["schema"], schema.get("name")
    # Already a JSON Schema object (has properties/type/etc.).
    return schema, None


def _normalise_schema(schema: Any) -> dict[str, Any] | None:
    """Accept a bare JSON Schema or a wrapper; return the bare schema."""
    return _schema_parts(schema)[0]


def _normalise_messages(
    messages: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pass through role/content, supporting both string and block content."""
    out: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {
            "role": message.get("role", "user"),
            "content": message.get("content", ""),
        }
        # Fireworks accepts reasoning_content on assistant turns; pass it along
        # when a caller re-injects it (agents/base.py does this).
        if message.get("reasoning_content"):
            item["reasoning_content"] = message["reasoning_content"]
        out.append(item)
    return out


class LLMProvider:
    """Wire-level client for the OpenAI-compatible inference API.

    Only this class performs HTTP. Everything else adapts it.
    """

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        self.api_key = resolve_api_key(api_key)
        self.is_mock = is_placeholder_key(self.api_key)
        self.timeout = timeout or REQUEST_TIMEOUT_S

        if self.is_mock:
            logger.warning(
                "LLM_API_KEY no configurada o inválida (¿una URL o placeholder?). "
                "Modo MOCK activo: no se harán llamadas reales."
            )

    # ── Payload construction ──────────────────────────────────────────

    def build_payload(
        self,
        *,
        model: Any,
        messages: Iterable[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        schema: Any = None,
        schema_mode: str = "json_schema",
        schema_name: str | None = None,
        repetition_penalty: float | None = None,
        frequency_penalty: float | None = None,
        top_p: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the request body sent to the provider."""
        tier = tier_of(model)
        settings = TierSettings.for_tier(tier)

        payload: dict[str, Any] = {
            "model": model_id_of(model),
            "messages": _normalise_messages(messages),
            "max_tokens": max_tokens or settings.max_tokens,
            "temperature": (
                settings.temperature if temperature is None else temperature
            ),
            "top_p": settings.top_p if top_p is None else top_p,
        }

        # Some providers (Fireworks) reject a body that carries
        # ``repetition_penalty`` together with ``frequency_penalty``/
        # ``presence_penalty`` — HTTP 400 even when one of them is the no-op
        # default. Send only the knob that actually alters sampling, and omit
        # no-op values entirely.
        rep = (
            settings.repetition_penalty
            if repetition_penalty is None
            else repetition_penalty
        )
        freq = (
            settings.frequency_penalty
            if frequency_penalty is None
            else frequency_penalty
        )
        if freq:
            payload["frequency_penalty"] = freq
        elif rep != 1.0:
            payload["repetition_penalty"] = rep

        schema_obj, schema_name_from_schema = _schema_parts(schema)
        if schema_obj:
            if schema_mode == "json_object":
                payload["response_format"] = {"type": "json_object"}
            else:
                # Fireworks rejects a bare schema in this slot: ``json_schema``
                # must be the OpenAI-style {"name", "schema"} wrapper.
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": (
                            schema_name
                            or schema_name_from_schema
                            or "structured_output"
                        ),
                        "schema": schema_obj,
                    },
                }

        if extra:
            payload.update(extra)
        return payload

    # ── Transport ─────────────────────────────────────────────────────

    def _post(
        self,
        payload: dict[str, Any],
        *,
        session_affinity: str | None = None,
    ) -> dict[str, Any]:
        import requests

        url = f"{api_base_url()}/chat/completions"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # Fireworks prompt caching only reuses a prefix within a single replica.
        # Pinning every request of a batch to the same replica is what turns a
        # stable prompt prefix into actual cache hits.
        if session_affinity:
            headers["x-session-affinity"] = str(session_affinity)
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except Exception as exc:  # network-level failure
            raise LLMProviderError(f"HTTP request failed: {exc}") from exc

        if response.status_code != 200:
            raise LLMProviderError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise LLMProviderError(f"invalid JSON response: {exc}") from exc

    # ── Public API ────────────────────────────────────────────────────

    def chat(
        self,
        *,
        model: Any,
        messages: Iterable[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        schema: Any = None,
        schema_mode: str = "json_schema",
        schema_name: str | None = None,
        repetition_penalty: float | None = None,
        frequency_penalty: float | None = None,
        top_p: float | None = None,
        extra: dict[str, Any] | None = None,
        session_affinity: str | None = None,
    ) -> LLMResponse:
        """Send one completion request and normalise the response.

        ``session_affinity`` is forwarded as ``x-session-affinity`` so that
        requests sharing a prompt prefix land on the same replica and hit the
        prompt cache (see https://docs.fireworks.ai/guides/prompt-caching).
        """
        payload = self.build_payload(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            schema=schema,
            schema_mode=schema_mode,
            schema_name=schema_name,
            repetition_penalty=repetition_penalty,
            frequency_penalty=frequency_penalty,
            top_p=top_p,
            extra=extra,
        )

        logger.info(
            "LLM call: model=%s tier=%s tokens_max=%d schema=%s",
            payload["model"],
            tier_of(model),
            payload["max_tokens"],
            (payload.get("response_format") or {}).get("type", "none"),
        )

        data = self._post(payload, session_affinity=session_affinity)
        choices = data.get("choices") or []
        if not choices:
            raise LLMProviderError(f"response has no choices: {str(data)[:300]}")

        message = choices[0].get("message") or {}
        usage = data.get("usage") or {}

        return LLMResponse(
            content=(message.get("content") or "").strip(),
            model=data.get("model") or payload["model"],
            tier=tier_of(model),
            reasoning_content=(message.get("reasoning_content") or ""),
            finish_reason=choices[0].get("finish_reason"),
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
            raw=data,
        )

    def mock_answer(self) -> str:
        """Deterministic canned completion used in mock mode."""
        return _MOCK_ANSWER


def parse_json_answer(
    content: str,
    *,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse an LLM JSON answer, tolerating code fences and stray braces.

    Shared so the heavy and fast workers stop carrying two divergent copies.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        lines = [ln for ln in text.split("\n")]
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Small models sometimes emit raw newlines/tabs inside strings.
        import re as _re

        repaired = _re.sub(
            r'"(.*?)"',
            lambda m: '"' + m.group(1).replace("\n", "\\n").replace("\t", "\\t") + '"',
            text,
            flags=_re.DOTALL,
        )
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return dict(default or {})
