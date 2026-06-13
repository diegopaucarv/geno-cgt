FROM python:3.13-slim
ENV PIP_CACHE_DIR=/app/.cache/pip
ENV HF_HOME=/app/.cache/huggingface
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY server.py .
RUN mkdir -p /app/.cache && chmod 777 /app/.cache
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
