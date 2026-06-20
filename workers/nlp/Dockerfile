FROM gt-base:latest
WORKDIR /app
COPY requirements.txt .
# Torch CPU-only evita ~1.5 GB de CUDA que stanza arrastraría
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
# NLP models are downloaded at runtime by app.core.nlp_models
# based on the user's language setting.
# Pre-install the most common model to avoid 568 MB download on every start.
RUN python -m spacy download es_core_news_lg

COPY . .
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "nlp"]
