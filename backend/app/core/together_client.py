"""
Together.ai LLM client.

Thin wrapper around the Together Python SDK.
All calls go through this module — never call the SDK directly.

Usage:
    from app.core.together_client import TogetherLLM

    client = TogetherLLM()
    response = client.chat(
        model="deepseek-ai/DeepSeek-R1",
        messages=[{"role": "user", "content": "..."}],
        response_format={"type": "json_object", "schema": {...}},
    )
"""

import hashlib
import json
import logging
import os
from typing import Any, Optional

from app.core.llm_config import (
    MODEL_REGISTRY,
    PROMPT_TIER_MAP,
    TIER_DEFAULT_MODEL,
    ModelEndpoint,
    get_model_for_prompt,
)
from together import Together

logger = logging.getLogger(__name__)


class TogetherLLM:
    """Unified client for Together.ai LLM inference."""

    def __init__(self, api_key: str | None = None):
        self._client = Together(api_key=api_key, timeout=600)
        self._call_count: dict[str, int] = {}
        self._total_cost_est: float = 0.0

    # ── Public API ────────────────────────────────────────────────────

    def chat(
        self,
        model: str | ModelEndpoint,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a chat completion request.

        Args:
            model: ModelEndpoint instance or model_id string.
            messages: List of {"role": "...", "content": "..."} dicts.
            max_tokens: Override default max_tokens. If None, uses model default.
            temperature: Override default temperature. If None, uses model default.
            response_format: Optional {"type": "json_object", "schema": {...}}.
        """
        endpoint = self._resolve_endpoint(model)

        kwargs: dict[str, Any] = {
            "model": endpoint.model_id,
            "messages": messages,
            "max_tokens": max_tokens or endpoint.max_tokens_default,
            "temperature": temperature or endpoint.temperature_default,
        }

        if response_format:
            kwargs["response_format"] = response_format

        logger.info(
            "LLM call: model=%s prompt_id=N/A tier=%s tokens_max=%d",
            endpoint.display_name,
            endpoint.tier,
            kwargs["max_tokens"],
        )

        response = self._client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content
        usage = response.usage

        self._call_count[endpoint.tier] = self._call_count.get(endpoint.tier, 0) + 1
        if usage:
            input_cost = (usage.prompt_tokens or 0) * self._cost_per_input_token(
                endpoint
            )
            output_cost = (usage.completion_tokens or 0) * self._cost_per_output_token(
                endpoint
            )
            self._total_cost_est += input_cost + output_cost

        return {
            "content": content,
            "model": endpoint.model_id,
            "tier": endpoint.tier,
            "usage": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            }
            if usage
            else None,
            "cost_est_input": input_cost if usage else 0,
            "cost_est_output": output_cost if usage else 0,
        }

    async def chat_stream(
        self,
        model: str | ModelEndpoint,
        messages: list[dict[str, str]],
        abort_event: Optional[Any] = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Streaming chat con soporte de abort.

        Si abort_event.is_set() → cierra stream → TCP disconnect →
        Together.ai detiene la inferencia inmediatamente.
        Solo se cobran los tokens generados hasta el corte.

        Args:
            abort_event: asyncio.Event. Si is_set(), corta la generación.
        """
        import asyncio

        endpoint = self._resolve_endpoint(model)

        kwargs: dict[str, Any] = {
            "model": endpoint.model_id,
            "messages": messages,
            "max_tokens": max_tokens or endpoint.max_tokens_default,
            "temperature": temperature or endpoint.temperature_default,
            "stream": True,
        }
        if response_format:
            kwargs["response_format"] = response_format

        logger.info(
            "LLM stream: model=%s tier=%s tokens_max=%d",
            endpoint.display_name,
            endpoint.tier,
            kwargs["max_tokens"],
        )

        stream = self._client.chat.completions.create(**kwargs)

        full_content = ""
        aborted = False
        try:
            for chunk in stream:
                if abort_event and (
                    (hasattr(abort_event, "is_set") and abort_event.is_set())
                    or (isinstance(abort_event, asyncio.Event) and abort_event.is_set())
                ):
                    aborted = True
                    stream.close()
                    break
                if chunk.choices[0].delta.content:
                    full_content += chunk.choices[0].delta.content
        finally:
            stream.close()

        return {
            "content": full_content,
            "model": endpoint.model_id,
            "tier": endpoint.tier,
            "aborted": aborted,
        }

    def chat_for_prompt(
        self,
        prompt_id: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a chat request, auto-resolving the model from the prompt_id.

        Uses PROMPT_TIER_MAP to determine which tier (pro/flash) → which model.
        """
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
        **kwargs,
    ) -> dict[str, Any]:
        """
        Build messages from a PromptTemplate and send to the correct model.

        This is the primary method agents should use.
        """
        payload = template.build_payload(**kwargs)
        endpoint = get_model_for_prompt(template.prompt_id)

        result = self.chat(
            model=endpoint,
            messages=payload["messages"],
            response_format=payload.get("response_format"),
        )

        # Store input hash for DB_EXEC_LOG traceability
        input_text = json.dumps(payload["messages"], sort_keys=True)
        result["prompt_id"] = template.prompt_id
        result["prompt_version"] = template.version
        result["prompt_hash"] = template.hash
        result["input_hash"] = hashlib.sha256(input_text.encode()).hexdigest()[:16]

        return result

    # ── Cost estimates (USD per 1M tokens — approximate) ─────────────

    @staticmethod
    def _cost_per_input_token(endpoint: ModelEndpoint) -> float:
        if endpoint.tier == "pro":
            return 2.50 / 1_000_000  # DeepSeek R1 ~ $2.50/M input
        return 0.27 / 1_000_000  # DeepSeek V3 ~ $0.27/M input

    @staticmethod
    def _cost_per_output_token(endpoint: ModelEndpoint) -> float:
        if endpoint.tier == "pro":
            return 8.00 / 1_000_000  # DeepSeek R1 ~ $8.00/M output
        return 1.10 / 1_000_000  # DeepSeek V3 ~ $1.10/M output

    # ── Helpers ───────────────────────────────────────────────────────

    def _resolve_endpoint(self, model: str | ModelEndpoint) -> ModelEndpoint:
        if isinstance(model, ModelEndpoint):
            return model
        if model in MODEL_REGISTRY:
            return MODEL_REGISTRY[model]
        if model in TIER_DEFAULT_MODEL:
            return MODEL_REGISTRY[TIER_DEFAULT_MODEL[model]]
        raise KeyError(f"Unknown model: {model}")

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "call_count": dict(self._call_count),
            "total_cost_est_usd": round(self._total_cost_est, 6),
        }
