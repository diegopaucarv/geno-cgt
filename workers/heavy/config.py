"""
Configuración centralizada para worker-heavy.

TODAS las credenciales se leen de variables de entorno inyectadas
por docker-compose. Este archivo es el SINGLE SOURCE OF TRUTH
para settings del worker.
"""

import os

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app_user:strongpass@pgbouncer:6432/gt-db",
)

# ── Redis ────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ── Together AI ──────────────────────────────────────────────────────
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

# ── Celery ───────────────────────────────────────────────────────────
CELERY_HMAC_SECRET = os.getenv("CELERY_HMAC_SECRET", "changeme")

# ── LLM Model Tiers ──────────────────────────────────────────────────
MODEL_FLASH = os.getenv("MODEL_FLASH", "google/gemma-4-31B-it")
MODEL_PRO = os.getenv("MODEL_PRO", "deepseek-ai/DeepSeek-V4")

# ── Environment ──────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
