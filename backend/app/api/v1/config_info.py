"""
Endpoint que expone configuración NO-SENSIBLE para el panel de config del frontend.

NUNCA expone secretos reales — solo nombres de variables, defaults seguros,
y metadata del sistema.
"""

from app.core.config import (
    ENVIRONMENT,
    MODEL_FLASH,
    MODEL_PRO,
    SEGMENTATION_MODE,
)
from app.core.llm_config import MODEL_REGISTRY, TIER_DEFAULT_MODEL
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["config"])


@router.get("/config")
async def get_config():
    """Devuelve config pública del backend (sin secretos)."""
    # Resolver modelos activos desde MODEL_REGISTRY
    pro_model = MODEL_REGISTRY.get(TIER_DEFAULT_MODEL.get("pro", ""))
    flash_model = MODEL_REGISTRY.get(TIER_DEFAULT_MODEL.get("flash", ""))

    return {
        "environment": ENVIRONMENT,
        "models": {
            "pro": {
                "tier": "pro",
                "model_id": pro_model.model_id if pro_model else MODEL_PRO,
                "display_name": pro_model.display_name if pro_model else "DeepSeek Pro",
                "max_tokens": pro_model.max_tokens_default if pro_model else 8192,
                "temperature": pro_model.temperature_default if pro_model else 0.3,
            },
            "flash": {
                "tier": "flash",
                "model_id": flash_model.model_id if flash_model else MODEL_FLASH,
                "display_name": flash_model.display_name
                if flash_model
                else "Gemma Flash",
                "max_tokens": flash_model.max_tokens_default if flash_model else 4096,
                "temperature": flash_model.temperature_default if flash_model else 0.1,
            },
        },
        "segmentation": {
            "mode": SEGMENTATION_MODE,
        },
        "auth": {
            "algorithm": "HS256",
            "token_type": "JWT (Bearer)",
        },
    }
