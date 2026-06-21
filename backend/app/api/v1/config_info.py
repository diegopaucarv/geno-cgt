"""
Config API — lectura y escritura de configuración runtime.

GET  /api/v1/config  → devuelve toda la config editable + defaults
PUT  /api/v1/config  → guarda overrides en runtime.json (persistente)

Los secrets NUNCA se exponen ni se persisten aquí.

Los defaults editables viven en app.core.defaults (fuente única).
"""

from typing import Any

from app.core.coding_styles import CODING_STYLES, get_default_styles
from app.core.config import (
    DEFAULT_OBJECT_OF_STUDY,
    DEFAULT_POPULATION_ASSUMPTION,
    ENVIRONMENT,
    GLASER_CLASSIFIER_PROMPT,
    MODEL_FLASH,
    MODEL_FLASH_MAX_TOKENS,
    MODEL_FLASH_REPETITION_PENALTY,
    MODEL_FLASH_TEMPERATURE,
    MODEL_FLASH_TOP_P,
    MODEL_PRO,
    MODEL_PRO_MAX_TOKENS,
    MODEL_PRO_TEMPERATURE,
    NLP_CONCURRENCY,
    ORCHESTRATION_MODE,
    SEGMENTATION_MODE,
    SEGMENTATION_REINERT,
    USE_GPU,
)
from app.core.nlp_models import SPACY_MODELS
from app.core.runtime_config import (
    get_config_value,
    get_runtime_config,
    update_runtime_config,
)
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["config"])


# ── spaCy model lookup by language ────────────────────────────────────


def _get_spacy_model() -> str:
    """Return the spaCy model name for the currently-configured language."""
    lang = get_config_value("NLP_LANGUAGE", default="es")
    return SPACY_MODELS.get(lang, SPACY_MODELS["es"])


# ── Schema for editable fields ───────────────────────────────────────


class LLMConfig(BaseModel):
    model_pro: str = "deepseek-ai/DeepSeek-V4-Pro"
    model_pro_max_tokens: int = 8192
    model_pro_temperature: float = 0.3
    model_flash: str = "nvidia/nemotron-3-ultra-550b-a55b"
    model_flash_max_tokens: int = 4096
    model_flash_temperature: float = 0.1
    model_flash_repetition_penalty: float = 1.1
    model_flash_top_p: float = 0.9


class SegmentationConfig(BaseModel):
    mode: str = "progressive"  # spacy | progressive | reinert
    reinert: bool = False
    nlp_concurrency: int = 1


class CGTConfig(BaseModel):
    population_assumption: str = ""
    object_of_study: str = "concern"
    coding_styles: list[str] = ["gerundio", "in_vivo"]
    glaser_classifier_prompt: str = ""  # Custom prompt for 3-step Glaser classifier


class SystemConfig(BaseModel):
    environment: str = "dev"
    orchestration_mode: str = "celery"
    use_gpu: bool = False


class RuntimeConfigUpdate(BaseModel):
    """Partial update — only send fields you want to change."""

    llm: LLMConfig | None = None
    segmentation: SegmentationConfig | None = None
    cgt: CGTConfig | None = None
    system: SystemConfig | None = None


# ── GET /config ──────────────────────────────────────────────────────


@router.get("/config")
async def get_config():
    """Devuelve toda la config editable con sus valores actuales."""
    runtime = get_runtime_config()

    # Coding styles from the library
    all_styles = [
        {
            "key": s.key,
            "name": s.name,
            "saldana_category": s.saldana_category,
            "examples": s.examples[:2],
        }
        for s in CODING_STYLES.values()
    ]
    active_styles = runtime.get("CODING_STYLES", get_default_styles())

    return {
        "llm": {
            "model_pro": MODEL_PRO,
            "model_pro_max_tokens": MODEL_PRO_MAX_TOKENS,
            "model_pro_temperature": MODEL_PRO_TEMPERATURE,
            "model_flash": MODEL_FLASH,
            "model_flash_max_tokens": MODEL_FLASH_MAX_TOKENS,
            "model_flash_temperature": MODEL_FLASH_TEMPERATURE,
            "model_flash_repetition_penalty": MODEL_FLASH_REPETITION_PENALTY,
            "model_flash_top_p": MODEL_FLASH_TOP_P,
            # Read-only: what the env var says (if set), for transparency
            "env_overrides": _env_overrides_section("llm"),
        },
        "segmentation": {
            "mode": SEGMENTATION_MODE,
            "reinert": SEGMENTATION_REINERT,
            "spacy_model": _get_spacy_model(),
            "nlp_concurrency": NLP_CONCURRENCY,
            "env_overrides": _env_overrides_section("segmentation"),
        },
        "cgt": {
            "population_assumption": DEFAULT_POPULATION_ASSUMPTION,
            "object_of_study": DEFAULT_OBJECT_OF_STUDY,
            "coding_styles": active_styles,
            "available_styles": all_styles,
            "glaser_classifier_prompt": GLASER_CLASSIFIER_PROMPT
            or "(using built-in default)",
            "env_overrides": _env_overrides_section("cgt"),
        },
        "system": {
            "environment": ENVIRONMENT,
            "orchestration_mode": ORCHESTRATION_MODE,
            "use_gpu": USE_GPU,
            "env_overrides": _env_overrides_section("system"),
        },
        "auth": {
            "algorithm": "HS256",
            "token_type": "JWT (Bearer)",
        },
        # What's currently in runtime.json (the persisted overrides)
        "_runtime_overrides": {
            k: v for k, v in runtime.items() if not k.startswith("_")
        },
    }


# ── PUT /config ──────────────────────────────────────────────────────


@router.put("/config")
async def save_config(
    body: RuntimeConfigUpdate,
    current_user: Usuario = Depends(get_current_user),
):
    """Guarda overrides de configuración en runtime.json (persiste en disco)."""
    updates: dict[str, Any] = {}

    if body.llm:
        updates.update(
            {
                "MODEL_PRO": body.llm.model_pro,
                "MODEL_PRO_MAX_TOKENS": str(body.llm.model_pro_max_tokens),
                "MODEL_PRO_TEMPERATURE": str(body.llm.model_pro_temperature),
                "MODEL_FLASH": body.llm.model_flash,
                "MODEL_FLASH_MAX_TOKENS": str(body.llm.model_flash_max_tokens),
                "MODEL_FLASH_TEMPERATURE": str(body.llm.model_flash_temperature),
                "MODEL_FLASH_REPETITION_PENALTY": str(
                    body.llm.model_flash_repetition_penalty
                ),
                "MODEL_FLASH_TOP_P": str(body.llm.model_flash_top_p),
            }
        )

    if body.segmentation:
        updates.update(
            {
                "SEGMENTATION_MODE": body.segmentation.mode,
                "SEGMENTATION_REINERT": str(body.segmentation.reinert).lower(),
                "NLP_CONCURRENCY": str(body.segmentation.nlp_concurrency),
            }
        )

    if body.cgt:
        updates.update(
            {
                "DEFAULT_POPULATION_ASSUMPTION": body.cgt.population_assumption,
                "DEFAULT_OBJECT_OF_STUDY": body.cgt.object_of_study,
                "CODING_STYLES": body.cgt.coding_styles,
                "GLASER_CLASSIFIER_PROMPT": body.cgt.glaser_classifier_prompt,
            }
        )

    if body.system:
        updates.update(
            {
                "ENVIRONMENT": body.system.environment,
                "ORCHESTRATION_MODE": body.system.orchestration_mode,
                "USE_GPU": str(body.system.use_gpu).lower(),
            }
        )

    if not updates:
        return {"status": "no_changes", "message": "No hay campos para actualizar"}

    new_config = update_runtime_config(updates)

    # Check which values are still overridden by env vars (can't be changed at runtime)
    blocked = {}
    for key in updates:
        env_name = key
        import os

        if os.getenv(env_name) is not None:
            blocked[key] = f"Bloqueado por variable de entorno ${env_name}"

    return {
        "status": "saved",
        "updated_fields": list(updates.keys()),
        "blocked_by_env": blocked or None,
        "message": (
            f"{len(updates)} campos guardados."
            + (f" {len(blocked)} bloqueados por env vars." if blocked else "")
        ),
    }


def _env_overrides_section(section: str) -> dict[str, str]:
    """Returns which env vars are currently overriding runtime config."""
    import os

    env_map = {
        "llm": [
            "MODEL_PRO",
            "MODEL_PRO_MAX_TOKENS",
            "MODEL_PRO_TEMPERATURE",
            "MODEL_FLASH",
            "MODEL_FLASH_MAX_TOKENS",
            "MODEL_FLASH_TEMPERATURE",
            "MODEL_FLASH_REPETITION_PENALTY",
            "MODEL_FLASH_TOP_P",
        ],
        "segmentation": [
            "SEGMENTATION_MODE",
            "SEGMENTATION_REINERT",
            "NLP_CONCURRENCY",
        ],
        "cgt": [
            "DEFAULT_POPULATION_ASSUMPTION",
            "DEFAULT_OBJECT_OF_STUDY",
            "GLASER_CLASSIFIER_PROMPT",
        ],
        "system": [
            "ENVIRONMENT",
            "ORCHESTRATION_MODE",
            "USE_GPU",
        ],
    }
    result = {}
    for key in env_map.get(section, []):
        val = os.getenv(key)
        if val is not None:
            result[key] = val
    return result
