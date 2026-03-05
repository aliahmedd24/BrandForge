# BrandForge — Production Container
# Python 3.11 + uv + ADK API server for Cloud Run

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Copy application code
COPY brandforge/ brandforge/

# Install the project itself
RUN uv sync --no-dev

# Cloud Run expects PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

# ADK API server serves the root_agent
CMD ["uv", "run", "adk", "api_server", "--port", "8080", "brandforge"]
