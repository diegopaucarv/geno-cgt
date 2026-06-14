FROM gt-base:latest
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "fast"]
