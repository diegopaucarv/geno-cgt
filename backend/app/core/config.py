"""
Configuración centralizada para el backend FastAPI.

Prioridad de resolución:
  1. Variable de entorno (docker-compose /.env)
  2. runtime.json (persistido desde el panel de config del frontend)
  3. Default hardcodeado (este archivo)

Clasificación:
  🔒 SECRETS — solo de env, NUNCA en runtime.json
  🏠 INTERNOS — defaults para dev, protegidos por login + red
  ⚙️ EDITABLE — expuesto en el panel ⚙ del frontend, persiste en runtime.json
"""

import os

from app.core.runtime_config import get_config_value

# ═══════════════════════════════════════════════════════════════════════
# 🔒 SECRETS REALES — solo de env, NUNCA expuestos ni persistidos
# ═══════════════════════════════════════════════════════════════════════

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-gt-local")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 365 * 100
REFRESH_TOKEN_EXPIRE_DAYS = 7

CELERY_HMAC_SECRET = os.getenv("CELERY_HMAC_SECRET", "dev-celery-hmac-gt-local")

# ═══════════════════════════════════════════════════════════════════════
# 🏠 INTERNOS — defaults para dev (no expuestos en panel)
# ═══════════════════════════════════════════════════════════════════════

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app_user:strongpass@pgbouncer:6432/gt-db",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "gt-documents")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

TEI_URL = os.getenv("TEI_URL", "http://tei:8080")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

# ═══════════════════════════════════════════════════════════════════════
# ⚙️ CONFIG EDITABLE — expuesto en el panel ⚙ del frontend
#    Prioridad: env var > runtime.json > EDITABLE_DEFAULTS (app.core.defaults)
# ═══════════════════════════════════════════════════════════════════════

from app.core.defaults import EDITABLE_DEFAULTS as _D


def _cfg(key: str) -> str:
    return get_config_value(key, default=_D.get(key, ""))


# ── LLM Models ───────────────────────────────────────────────────────

MODEL_PRO = _cfg("MODEL_PRO")
MODEL_PRO_MAX_TOKENS = int(_cfg("MODEL_PRO_MAX_TOKENS"))
MODEL_PRO_TEMPERATURE = float(_cfg("MODEL_PRO_TEMPERATURE"))

MODEL_FLASH = _cfg("MODEL_FLASH")
MODEL_FLASH_MAX_TOKENS = int(_cfg("MODEL_FLASH_MAX_TOKENS"))
MODEL_FLASH_TEMPERATURE = float(_cfg("MODEL_FLASH_TEMPERATURE"))
MODEL_FLASH_REPETITION_PENALTY = float(_cfg("MODEL_FLASH_REPETITION_PENALTY"))
MODEL_FLASH_TOP_P = float(_cfg("MODEL_FLASH_TOP_P"))

# ── Segmentation ─────────────────────────────────────────────────────

SEGMENTATION_MODE = _cfg("SEGMENTATION_MODE")
SEGMENTATION_REINERT = _cfg("SEGMENTATION_REINERT").lower() in ("1", "true", "yes")
NLP_CONCURRENCY = int(_cfg("NLP_CONCURRENCY"))

# ── CGT Methodology ──────────────────────────────────────────────────

DEFAULT_POPULATION_ASSUMPTION = _cfg("DEFAULT_POPULATION_ASSUMPTION")
DEFAULT_OBJECT_OF_STUDY = _cfg("DEFAULT_OBJECT_OF_STUDY")

# ── Glaser Classifier ────────────────────────────────────────────────
GLASER_CLASSIFIER_PROMPT = os.getenv(
    "GLASER_CLASSIFIER_PROMPT", ""
)  # Overridable via env var for the 3-step classifier

# ── System ───────────────────────────────────────────────────────────

ENVIRONMENT = _cfg("ENVIRONMENT")
ORCHESTRATION_MODE = _cfg("ORCHESTRATION_MODE")
USE_GPU = _cfg("USE_GPU").lower() in ("1", "true", "yes")
