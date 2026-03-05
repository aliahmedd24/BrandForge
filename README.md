# BrandForge

> AI-Powered Multi-Agent Marketing Platform  
> **Hackathon Category:** Creative Storyteller (Google Gemini / ADK)  
> **Architecture:** 11 agents · 8 GCP services · ADK + MCP + A2A

---

## Quick Start

### Prerequisites

- Python 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (gcloud CLI)
- GCP project with billing enabled

### Setup

```bash
# 1. Clone and enter the project
cd BrandForge

# 2. Copy env template and add your API key
cp .env.example .env.local
# Edit .env.local with your GEMINI_API_KEY

# 3. Install dependencies
uv sync

# 4. (Optional) Provision GCP services
export GCP_PROJECT_ID=brandforge-489114
./scripts/bootstrap.sh
./scripts/seed_secrets.sh

# 5. Run unit tests (no GCP needed)
uv run pytest tests/infra/test_models.py tests/infra/test_secrets.py -v

# 6. Run infrastructure tests (requires GCP)
uv run pytest tests/infra/ -v

# 7. Start ADK dev server
adk web
```

### Development Commands

```bash
# Tests
uv run pytest -v                         # All tests
uv run pytest tests/infra/ -v            # Infrastructure tests only
uv run pytest --cov=brandforge -v        # With coverage

# Linting
uv run ruff check .                      # Lint
uv run mypy brandforge/                  # Type check

# ADK
adk web                                  # Local dev server
adk check-agent brandforge.agent:root_agent  # Validate agent

# Docker
docker build -t brandforge .             # Build container
docker run -p 8080:8080 brandforge       # Run locally
```

---

## Project Structure

```
brandforge/
├── pyproject.toml              # Python project config (uv)
├── brandforge/
│   ├── agent.py                # Root ADK agent (exports root_agent)
│   ├── shared/
│   │   ├── config.py           # Secrets + config loading
│   │   ├── models.py           # ALL Pydantic schemas
│   │   ├── firestore.py        # Firestore client + CRUD
│   │   ├── storage.py          # GCS helpers
│   │   └── pubsub.py           # Pub/Sub publishing
│   └── agents/                 # Sub-agent modules (Phase 1+)
├── tests/infra/                # Infrastructure integration tests
├── scripts/
│   ├── bootstrap.sh            # GCP provisioning
│   └── seed_secrets.sh         # Secret Manager seeding
├── Dockerfile                  # Production container
├── cloudbuild.yaml             # CI/CD pipeline
└── deploy/cloudrun/
    └── service.yaml            # Cloud Run service config
```

---

## Architecture

BrandForge is built on **Google ADK** with 11 specialized agents communicating
via **Pub/Sub** (A2A pattern). All agents are hosted on **Cloud Run**, state
lives in **Firestore**, assets in **GCS**, and social posting uses **MCP**.

See `brandforge-prd/README.md` for the full phase roadmap.

---

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 0 — Foundation | ✅ Complete | GCP scaffold, ADK setup, shared schemas |
| 1 — Brand Strategist | 🔲 Planned | Brand DNA generation |
| 2 — Production Agents | 🔲 Planned | Scripts, images, videos, copy |
| 3 — QA Inspector | 🔲 Planned | Multimodal QA scoring |
| 4 — Live Canvas UI | 🔲 Planned | Real-time streaming UI |
| 5 — Distribution | 🔲 Planned | MCP social posting |
| 6 — Analytics | 🔲 Planned | BigQuery + A2A loop |
| 7 — Advanced Intelligence | 🔲 Planned | Trends, memory, Sage voice |
| 8 — Demo Hardening | 🔲 Planned | Demo script + submission |
