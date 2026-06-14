FROM gt-base:latest
ARG USE_GPU=false
ENV PIP_CACHE_DIR=/app/.cache/pip
ENV HF_HOME=/app/.cache/huggingface
RUN rm -rf /app/.cache && mkdir -p /app/.cache && chmod 777 /app/.cache
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
# GPU: cambia onnxruntime → onnxruntime-gpu (optimum.onnxruntime funciona con ambos)
RUN if [ "$USE_GPU" = "true" ]; then \
        pip uninstall -y onnxruntime && pip install onnxruntime-gpu; \
    fi
COPY server.py .
RUN mkdir -p /app/.cache && chmod 777 /app/.cache
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
