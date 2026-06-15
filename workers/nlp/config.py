"""
Configuración centralizada para worker-nlp.

TODAS las credenciales se leen de variables de entorno inyectadas
por docker-compose. Este archivo es el SINGLE SOURCE OF TRUTH
para settings del worker.
"""

import os

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app_user:strongpass@postgres:5432/gt-db",
)

# ── Redis ────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ── TEI ──────────────────────────────────────────────────────────────
TEI_URL = os.getenv("TEI_URL", "http://tei:8080")

# ── Celery ───────────────────────────────────────────────────────────
CELERY_HMAC_SECRET = os.getenv("CELERY_HMAC_SECRET", "changeme")

# ── Segmentation ─────────────────────────────────────────────────────
SEGMENTATION_REINERT = os.getenv("SEGMENTATION_REINERT", "true").lower() in (
    "1",
    "true",
    "yes",
)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

# ── Environment ──────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
