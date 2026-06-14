FROM gt-base:latest
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
COPY . .
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "fast"]
