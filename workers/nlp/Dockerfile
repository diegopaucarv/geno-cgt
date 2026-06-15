FROM gt-base:latest
WORKDIR /app
COPY requirements.txt .
# Torch CPU-only evita ~1.5 GB de CUDA que stanza arrastraría
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
RUN python -m spacy download es_core_news_lg
# Pre-descargar Stanza para evitar fallos de red en runtime
RUN python3 -c "import stanza; stanza.download('es', processors='tokenize,pos,lemma,depparse,constituency,coref')"
# Pre-descargar modelo transformer del coref (necesita network)
RUN python3 -c "import stanza; p = stanza.Pipeline('es', processors='tokenize,pos,lemma,depparse,constituency,coref'); print('Coref ready')" 2>/dev/null; true
COPY . .
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "nlp"]
