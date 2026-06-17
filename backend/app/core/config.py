"""
Configuración centralizada para el backend FastAPI.

Clasificación de defaults:
  🔒 SECRETS REALES — SIN default seguro, deben venir del entorno en producción:
     TOGETHER_API_KEY, JWT_SECRET_KEY, CELERY_HMAC_SECRET

  🏠 INTERNOS — defaults para dev local. Protegidos por la capa de login + red:
     DATABASE_URL, MINIO_*, REDIS_URL

  ⚙️ CONFIG — no son secretos, son opciones de operación:
     SEGMENTATION_MODE, MODEL_FLASH, MODEL_PRO, ENVIRONMENT, etc.

En producción, los SECRETS REALES se inyectan desde GitHub Secrets.
"""

import os

# ═══════════════════════════════════════════════════════════════════════
# 🔒 SECRETS REALES — SIN DEFAULT SEGURO
# ═══════════════════════════════════════════════════════════════════════

# Together AI — API key de facturación. Obligatorio para funcionar.
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

# JWT — firma de tokens de sesión. En producción DEBE ser un valor aleatorio.
# Generar: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-gt-local")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 365 * 100  # nunca
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Celery — firma HMAC de tareas. En producción DEBE ser aleatorio.
CELERY_HMAC_SECRET = os.getenv("CELERY_HMAC_SECRET", "dev-celery-hmac-gt-local")

# ═══════════════════════════════════════════════════════════════════════
# 🏠 INTERNOS — defaults seguros para dev (protegidos por login + red)
# ═══════════════════════════════════════════════════════════════════════

# Database
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app_user:strongpass@pgbouncer:6432/gt-db",
)

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "gt-documents")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# TEI (Text Embeddings Inference)
TEI_URL = os.getenv("TEI_URL", "http://tei:8080")

# ═══════════════════════════════════════════════════════════════════════
# ⚙️ CONFIG — opciones de operación, no secretos
# ═══════════════════════════════════════════════════════════════════════

# LLM Model Tiers
MODEL_FLASH = os.getenv("MODEL_FLASH", "google/gemma-4-31B-it")
MODEL_PRO = os.getenv("MODEL_PRO", "deepseek-ai/DeepSeek-V4")

# Segmentation
SEGMENTATION_MODE = os.getenv("SEGMENTATION_MODE", "spacy")
SEGMENTATION_REINERT = os.getenv("SEGMENTATION_REINERT", "false").lower() in (
    "1",
    "true",
    "yes",
)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# Orchestration
ORCHESTRATION_MODE = os.getenv("ORCHESTRATION_MODE", "celery")

# CGT Methodology Defaults
DEFAULT_POPULATION_ASSUMPTION = os.getenv(
    "DEFAULT_POPULATION_ASSUMPTION",
    "hábitos hipotéticos de comportamiento que procesan "
    "preocupaciones similares o más amplias en la vida diaria "
    "del entrevistado",
)
DEFAULT_OBJECT_OF_STUDY = os.getenv("DEFAULT_OBJECT_OF_STUDY", "concern")
# concern | emotion | behavior | discourse | identity | custom
