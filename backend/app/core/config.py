"""
Configuración centralizada para el backend FastAPI.

TODAS las credenciales y settings se leen de variables de entorno.
Los defaults aquí son para desarrollo local; en producción se inyectan
vía docker-compose.yml + .env.

Este es el SINGLE SOURCE OF TRUTH para settings del backend.
"""

import os

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app_user:strongpass@pgbouncer:6432/gt-db",
)

# ── Redis ────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ── MinIO ────────────────────────────────────────────────────────────
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "gt-documents")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# ── JWT / Auth ───────────────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# ── TEI (Text Embeddings Inference) ──────────────────────────────────
TEI_URL = os.getenv("TEI_URL", "http://tei:8080")

# ── Together AI ──────────────────────────────────────────────────────
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

# ── Celery ───────────────────────────────────────────────────────────
CELERY_HMAC_SECRET = os.getenv("CELERY_HMAC_SECRET", "changeme")

# ── LLM Model Tiers ──────────────────────────────────────────────────
MODEL_FLASH = os.getenv("MODEL_FLASH", "deepseek-ai/DeepSeek-V3")
MODEL_PRO = os.getenv("MODEL_PRO", "deepseek-ai/DeepSeek-R1")

# ── Segmentation ─────────────────────────────────────────────────────
SEGMENTATION_MODE = os.getenv("SEGMENTATION_MODE", "spacy")
SEGMENTATION_REINERT = os.getenv("SEGMENTATION_REINERT", "true").lower() in (
    "1",
    "true",
    "yes",
)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

# ── Environment ──────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# ── Orchestration ────────────────────────────────────────────────────
ORCHESTRATION_MODE = os.getenv("ORCHESTRATION_MODE", "celery")
