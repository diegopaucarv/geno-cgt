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
#    Prioridad: env var > runtime.json > default
# ═══════════════════════════════════════════════════════════════════════

# ── LLM Models ───────────────────────────────────────────────────────

MODEL_PRO = get_config_value("MODEL_PRO", default="deepseek-ai/DeepSeek-V4")
MODEL_PRO_MAX_TOKENS = int(get_config_value("MODEL_PRO_MAX_TOKENS", default="8192"))
MODEL_PRO_TEMPERATURE = float(get_config_value("MODEL_PRO_TEMPERATURE", default="0.3"))

MODEL_FLASH = get_config_value("MODEL_FLASH", default="google/gemma-4-31B-it")
MODEL_FLASH_MAX_TOKENS = int(get_config_value("MODEL_FLASH_MAX_TOKENS", default="4096"))
MODEL_FLASH_TEMPERATURE = float(
    get_config_value("MODEL_FLASH_TEMPERATURE", default="0.1")
)
MODEL_FLASH_REPETITION_PENALTY = float(
    get_config_value("MODEL_FLASH_REPETITION_PENALTY", default="1.1")
)
MODEL_FLASH_TOP_P = float(get_config_value("MODEL_FLASH_TOP_P", default="0.9"))

# ── Segmentation ─────────────────────────────────────────────────────

SEGMENTATION_MODE = get_config_value("SEGMENTATION_MODE", default="spacy")
SEGMENTATION_REINERT = get_config_value(
    "SEGMENTATION_REINERT", default="false"
).lower() in (
    "1",
    "true",
    "yes",
)
SPACY_MODEL = get_config_value("SPACY_MODEL", default="es_core_news_lg")
NLP_CONCURRENCY = int(get_config_value("NLP_CONCURRENCY", default="1"))

# ── CGT Methodology ──────────────────────────────────────────────────

DEFAULT_POPULATION_ASSUMPTION = get_config_value(
    "DEFAULT_POPULATION_ASSUMPTION",
    default=(
        "hábitos hipotéticos de comportamiento que procesan "
        "preocupaciones similares o más amplias en la vida diaria "
        "del entrevistado"
    ),
)
DEFAULT_OBJECT_OF_STUDY = get_config_value("DEFAULT_OBJECT_OF_STUDY", default="concern")

# ── System ───────────────────────────────────────────────────────────

ENVIRONMENT = get_config_value("ENVIRONMENT", default="dev")
ORCHESTRATION_MODE = get_config_value("ORCHESTRATION_MODE", default="celery")
USE_GPU = get_config_value("USE_GPU", default="false").lower() in ("1", "true", "yes")
