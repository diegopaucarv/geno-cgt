FROM gt-base:latest
WORKDIR /app
COPY requirements.txt .
# Torch CPU-only evita ~1.5 GB de CUDA que stanza arrastraría
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
RUN python -m spacy download es_core_news_lg
COPY . .
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "nlp"]
