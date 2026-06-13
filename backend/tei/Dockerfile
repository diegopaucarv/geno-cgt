FROM python:3.11-slim

WORKDIR /app

# Instalamos git solo porque trust_remote_code a veces lo usa internamente para verificar repos
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

RUN mkdir -p /app/.cache && chmod 777 /app/.cache
ENV HF_HOME=/app/.cache

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
