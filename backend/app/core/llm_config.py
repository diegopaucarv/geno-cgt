"""
Together.ai model configuration and routing.

Defines which Together.ai model endpoints to use for each tier:
- RAZONAMIENTO_POTENTE: DeepSeek Pro (complex reasoning, CGT methodology)
- RÁPIDO_ECONÓMICO: DeepSeek Flash (fast extraction, volume tasks)

Also defines the prompt profile -> model mapping.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ModelEndpoint:
    """A Together.ai model endpoint configuration."""

    model_id: str  # e.g. "deepseek-ai/DeepSeek-R1"
    display_name: str  # e.g. "DeepSeek Pro"
    tier: str  # "pro" | "flash"
    max_tokens_default: int
    temperature_default: float
    supports_json_schema: bool = True
    notes: str = ""


# ── Together.ai Model Registry ──────────────────────────────────────────

MODEL_REGISTRY: dict[str, ModelEndpoint] = {
    # ── PRO tier: DeepSeek V4 Pro via Together.ai ──────────────────
    "deepseek-pro": ModelEndpoint(
        model_id=os.getenv("MODEL_PRO", "deepseek-ai/DeepSeek-V4-Pro"),
        display_name="DeepSeek Pro (V4)",
        tier="pro",
        max_tokens_default=int(os.getenv("MODEL_PRO_MAX_TOKENS", "8192")),
        temperature_default=float(os.getenv("MODEL_PRO_TEMPERATURE", "0.3")),
        supports_json_schema=True,
        notes=(
            "Reasoning model. Do NOT use 'think step by step' in prompts — "
            "it interferes with the native chain-of-thought. Use staged context: "
            "provide [Objetivo], [Contexto], [Restricciones] clearly separated. "
            "Demand evidence: 'Usa solo la información proporcionada.'"
        ),
    ),
    # ── FLASH tier: Gemma 4 via Together.ai ───────────────────────
    "deepseek-flash": ModelEndpoint(
        model_id=os.getenv("MODEL_FLASH", "google/gemma-4-31B-it"),
        display_name="Gemma 4 Flash (31B)",
        tier="flash",
        max_tokens_default=int(os.getenv("MODEL_FLASH_MAX_TOKENS", "4096")),
        temperature_default=float(os.getenv("MODEL_FLASH_TEMPERATURE", "0.1")),
        supports_json_schema=True,
        notes=(
            "Fast model for volume tasks. Add explicit guardrails: "
            "'NO intentes usar herramientas externas.' "
            "Divide complex tasks into chained prompts."
        ),
    ),
}


# ── Tier → default model mapping ───────────────────────────────────────

TIER_DEFAULT_MODEL: dict[str, str] = {
    "pro": "deepseek-pro",
    "flash": "deepseek-flash",
}


# ── Prompt ID → tier mapping (which prompts need which model) ──────────

PROMPT_TIER_MAP: dict[str, str] = {
    # === PRO (DeepSeek R1 — complex reasoning) ===
    "batch_coder_producer": "pro",
    "batch_coder_critic": "pro",
    "map_synthesis": "pro",
    "reduce_synthesis": "pro",
    "hypothesis_generation": "pro",
    "hypothesis_testing": "pro",
    "core_concern_finder": "pro",
    "latent_construct_analysis": "pro",
    "memo_proposer": "pro",
    "memo_tester": "pro",
    "memo_rewriter": "pro",
    "paradigm_integrator": "pro",
    "group_comparison": "pro",
    "variable_derivation": "pro",
    "hypothesis_consolidation": "pro",
    "clusterizador_informado": "pro",
    "agrupador_constructos": "pro",
    "selective_structure_a": "pro",
    "selective_structure_b": "pro",
    # === FLASH (DeepSeek V3 — fast extraction / volume) ===
    "entity_extraction": "flash",
    "incident_extractor": "flash",
    "document_classifier": "flash",
    "json_schema_generator": "flash",
    "document_summarizer": "flash",
    "topic_namer": "flash",
    "context_synthesizer": "flash",
    "insight_grouping": "flash",
    "thematic_clusters": "flash",
    "join_segments": "flash",
    "saturation_cats_vs_incidents": "flash",
    "saturation_cats_vs_props": "flash",
    "saturation_cats_vs_cats": "flash",
    "recode_documents": "flash",
    "resegmenter": "flash",
    "text_cleaner": "flash",
}


def get_model_for_prompt(prompt_id: str) -> ModelEndpoint:
    """Resolve which model to use for a given prompt ID."""
    tier = PROMPT_TIER_MAP.get(prompt_id)
    if tier is None:
        raise KeyError(f"Unknown prompt_id: {prompt_id}. Add it to PROMPT_TIER_MAP.")
    model_key = TIER_DEFAULT_MODEL[tier]
    return MODEL_REGISTRY[model_key]


def get_model_for_tier(tier: str) -> ModelEndpoint:
    """Resolve the default model for a tier."""
    model_key = TIER_DEFAULT_MODEL.get(tier)
    if model_key is None:
        raise KeyError(f"Unknown tier: {tier}. Use 'pro' or 'flash'.")
    return MODEL_REGISTRY[model_key]
