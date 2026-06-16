"""
Configuración centralizada para worker-nlp.

TODAS las credenciales se leen de variables de entorno inyectadas
por docker-compose. Este archivo es el SINGLE SOURCE OF TRUTH
para settings del worker.

Perfiles de memoria (NLP_PROFILE):
  low  → 8GB, concurrency=1, spaCy sin vectors (default, PC con poca RAM)
  high → 12GB, concurrency=2, spaCy completo (servidor con RAM generosa)

Overrides individuales:
  SPACY_MODEL, SPACY_EXCLUDE, NLP_CONCURRENCY, NLP_MEM_LIMIT
  (tienen prioridad sobre el perfil)
"""

import os

# ── Profiles ──────────────────────────────────────────────────────────
NLP_PROFILE = os.getenv("NLP_PROFILE", "low")

_PROFILES: dict[str, dict[str, str]] = {
    "low": {
        "SPACY_EXCLUDE": "vectors,lemmatizer",
        "CONCURRENCY": "1",
        "MEM_LIMIT": "8g",
    },
    "high": {
        "SPACY_EXCLUDE": "",
        "CONCURRENCY": "2",
        "MEM_LIMIT": "12g",
    },
}
_profile = _PROFILES.get(NLP_PROFILE, _PROFILES["low"])

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
SEGMENTATION_REINERT = os.getenv("SEGMENTATION_REINERT", "false").lower() in (
    "1",
    "true",
    "yes",
)
SPACY_MODEL = os.getenv("SPACY_MODEL", "es_core_news_lg")
# SPACY_EXCLUDE: "auto" = detect at runtime, "" = load all, "vectors,lemmatizer" = manual
SPACY_EXCLUDE = os.getenv("SPACY_EXCLUDE", "auto")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

# ── Runtime settings (used by docker-compose via env vars) ───────────
# These are exported so docker-compose can read them as ${VAR}
NLP_CONCURRENCY = os.getenv("NLP_CONCURRENCY", _profile["CONCURRENCY"])
NLP_MEM_LIMIT = os.getenv("NLP_MEM_LIMIT", _profile["MEM_LIMIT"])

# ── Environment ──────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
