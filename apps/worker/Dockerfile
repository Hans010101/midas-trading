FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=4"]
