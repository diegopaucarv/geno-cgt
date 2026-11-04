# Single multi-stage Dockerfile for every Python image in the stack.
#
# Targets: backend, worker-fast, worker-heavy, worker-nlp, tei
#
# Every target shares the `base` stage, so there is no longer a separate
# `gt-base` image to build first. Compose can build all targets in parallel
# because the FROM edges are resolved inside this file.
#
#   docker build --target backend -t geno-cgt-fastapi .

FROM python:3.13-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential git curl libmagic1 \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel


# ---------------------------------------------------------------------------
# FastAPI backend
# ---------------------------------------------------------------------------
FROM base AS backend

WORKDIR /app

COPY backend/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# NLP models are downloaded at runtime by app.core.nlp_models
# based on the user's language setting

COPY backend/ .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app"]


# ---------------------------------------------------------------------------
# Celery worker — queue "fast"
# ---------------------------------------------------------------------------
FROM base AS worker-fast

WORKDIR /app

COPY workers/fast/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY workers/fast/ .

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "fast"]


# ---------------------------------------------------------------------------
# Celery worker — queue "heavy"
# ---------------------------------------------------------------------------
FROM base AS worker-heavy

WORKDIR /app

COPY workers/heavy/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY workers/heavy/ .

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "heavy"]


# ---------------------------------------------------------------------------
# Celery worker — queue "nlp"
# ---------------------------------------------------------------------------
FROM base AS worker-nlp

WORKDIR /app

COPY workers/nlp/requirements.txt .

# Torch CPU-only evita ~1.5 GB de CUDA que stanza arrastraría
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# NLP models are downloaded at runtime by app.core.nlp_models
# based on the user's language setting.
# Pre-install the most common model to avoid 568 MB download on every start.
RUN python -m spacy download es_core_news_lg

COPY workers/nlp/ .

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "nlp"]


# ---------------------------------------------------------------------------
# TEI-compatible embedding server
# ---------------------------------------------------------------------------
FROM base AS tei

ARG USE_GPU=false
ENV PIP_CACHE_DIR=/app/.cache/pip
ENV HF_HOME=/app/.cache/huggingface
RUN rm -rf /app/.cache && mkdir -p /app/.cache && chmod 777 /app/.cache

WORKDIR /app

COPY backend/tei/requirements.txt .

# torch CPU primero: si no, pip resuelve el build CUDA de PyPI (~4 GB)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# GPU: cambia onnxruntime → onnxruntime-gpu (optimum.onnxruntime funciona con ambos)
RUN if [ "$USE_GPU" = "true" ]; then \
    pip uninstall -y onnxruntime && pip install onnxruntime-gpu; \
    fi

COPY backend/tei/server.py .
RUN mkdir -p /app/.cache && chmod 777 /app/.cache

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
