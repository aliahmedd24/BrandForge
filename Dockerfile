FROM python:3.11-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency specification first for layer caching
COPY pyproject.toml ./

# Install dependencies (no venv needed in container)
RUN uv pip install --system --no-cache .

# Copy application code
COPY brandforge/ ./brandforge/

# ADK api_server serves the agent over HTTP
ENV PORT=8080
EXPOSE 8080

CMD ["adk", "api_server", "--port", "8080", "brandforge"]
