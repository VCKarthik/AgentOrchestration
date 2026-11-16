# Project AMP — shared root Dockerfile
# All agents build from repo root using this file.
# CMD is overridden per service in docker-compose.yml.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy entire repo — each service selects its own entry point via CMD
COPY . .

# Qdrant store and SQLite state are mounted as volumes at runtime
RUN mkdir -p /app/infra /app/data/outputs /app/logs /app/output
