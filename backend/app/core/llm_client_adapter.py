"""
Backend LLM adapter.

``TogetherLLM`` is retained as the public name so existing call sites keep
working, but it no longer knows anything about any particular vendor: every
call is delegated to :class:`app.config.core.llm_client.LLMProvider`.

Schema enforcement: :meth:`TogetherLLM.invoke_prompt` sends the prompt's
``output_schema`` to the provider as an enforced ``json_schema``
``response_format``, so the model is constrained server-side instead of
relying on "please answer in JSON" instructions in the prompt text.

Usage:
    from app.core.llm_client_adapter import TogetherLLM

    client = TogetherLLM()
    response = client.chat(
        model="deepseek-pro",
        messages=[{"role": "user", "content": "..."}],
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from app.core.llm_client import (
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    model_id_of,
    tier_of,
)
from app.core.llm_config import (
    MODEL_REGISTRY,
    PROMPT_TIER_MAP,
    TIER_DEFAULT_MODEL,
    ModelEndpoint,
    get_model_for_prompt,
)

logger = logging.getLogger(__name__)


class TogetherLLM:
    """Unified LLM client for the backend (provider-agnostic).

    The name is historical; the implementation is :class:`LLMProvider`.
    """

    def __init__(self, api_key: str | None = None):
        self._provider = LLMProvider(api_key=api_key)
        self._call_count: dict[str, int] = {}
        self.is_mock = self._provider.is_mock

    # ── Public API ────────────────────────────────────────────────────

    def chat(
        self,
        model: str | ModelEndpoint | None,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Args:
            model: ModelEndpoint, registry key, tier name or provider model id.
            messages: ``{"role", "content"}`` dicts; ``content`` may be a
                string or a list of multimodal content blocks.
            max_tokens: Override the tier default.
            temperature: Override the tier default.
            response_format: Enforced output format. Either a bare JSON Schema,
                ``{"schema": ...}`` or ``{"type": "json_object"}``.
            schema: Convenience alternative to ``response_format``.
        """
        schema_mode, schema_obj, schema_name = _split_response_format(
            response_format, schema
        )
        tier = tier_of(model)

        try:
            response: LLMResponse = self._provider.chat(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                schema=schema_obj,
                schema_mode=schema_mode,
                schema_name=schema_name,
            )
        except LLMProviderError as exc:
            logger.error("LLM call failed: %s", exc)
            raise

        self._call_count[tier] = self._call_count.get(tier, 0) + 1
        return response.to_result(reasoning_content=response.reasoning_content)

    def chat_for_prompt(
        self,
        prompt_id: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Chat resolving the model from ``prompt_id`` via ``PROMPT_TIER_MAP``."""
        endpoint = get_model_for_prompt(prompt_id)
        return self.chat(
            model=endpoint,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )

    def invoke_prompt(
        self,
        template,  # PromptTemplate
        language: str = "en",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build messages from a PromptTemplate and call the routed model.

        The template's ``output_schema`` (or its translated
        ``schema.<language>.json``) is enforced via ``json_schema``.
        """
        payload = template.build_payload(language=language, **kwargs)
        endpoint = get_model_for_prompt(template.prompt_id)

        result = self.chat(
            model=endpoint,
            messages=payload["messages"],
            response_format=payload.get("response_format"),
        )

        input_text = json.dumps(payload["messages"], sort_keys=True, default=str)
        result.update(
            {
                "prompt_id": template.prompt_id,
                "prompt_version": template.version,
                "prompt_hash": template.hash,
                "input_hash": hashlib.sha256(input_text.encode()).hexdigest()[:16],
            }
        )
        return result

    async def chat_stream(
        self,
        model: str | ModelEndpoint | None,
        messages: list[dict[str, Any]],
        abort_event: Optional[Any] = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming compatibility shim.

        The unified provider issues non-streaming requests only; this keeps the
        historical signature working for callers that pass ``abort_event``.
        """
        import asyncio

        result = await asyncio.to_thread(
            self.chat,
            model,
            messages,
            max_tokens,
            temperature,
            response_format,
        )
        aborted = bool(
            abort_event is not None
            and hasattr(abort_event, "is_set")
            and abort_event.is_set()
        )
        return {
            "content": result.get("content", ""),
            "model": result.get("model"),
            "tier": result.get("tier"),
            "aborted": aborted,
        }

    # ── Introspection ─────────────────────────────────────────────────

    def _resolve_endpoint(self, model: str | ModelEndpoint) -> ModelEndpoint:
        if isinstance(model, ModelEndpoint):
            return model
        if model in MODEL_REGISTRY:
            return MODEL_REGISTRY[model]
        if str(model).lower() in TIER_DEFAULT_MODEL:
            return MODEL_REGISTRY[TIER_DEFAULT_MODEL[str(model).lower()]]
        raise KeyError(f"Unknown model: {model}")

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "call_count": dict(self._call_count),
            "model_pro": model_id_of("deepseek-pro"),
            "model_flash": model_id_of("deepseek-flash"),
        }


def _split_response_format(
    response_format: dict[str, Any] | None,
    schema: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Interpret a ``response_format`` dict into (mode, schema, name)."""
    if schema:
        return "json_schema", schema, None
    if not response_format:
        return "json_schema", None, None

    fmt_type = response_format.get("type")
    if fmt_type == "json_object":
        return "json_object", None, None
    if fmt_type == "json_schema":
        inner = response_format.get("json_schema") or {}
        # The provider re-wraps the schema, so pass the name back to it.
        return "json_schema", inner.get("schema", inner) or None, inner.get("name")
    # A bare schema was passed directly.
    return "json_schema", response_format, None


# Re-exported so callers can keep importing from one place.
__all__ = ["TogetherLLM", "PROMPT_TIER_MAP", "get_model_for_prompt"]
