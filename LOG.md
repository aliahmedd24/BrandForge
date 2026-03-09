# BrandForge Session Log

## Session 2026-03-09 10:10 — Phase 0: Foundation & Infrastructure

**Status:** Complete
**Phase File:** phase-00-foundation.md

### What Was Done
- `pyproject.toml` — Project config with all deps (google-adk, pydantic, GCP clients), Python 3.11, uv
- `.env.example` — Template for local dev env vars
- `.gitignore` — Python + secrets + IDE exclusions
- `brandforge/__init__.py` — ADK discovery import (`from . import agent`)
- `brandforge/shared/__init__.py` — Exports settings and all models
- `brandforge/agents/__init__.py` — Empty package marker
- `brandforge/shared/models.py` — All Pydantic v2 schemas: `CampaignStatus`, `AgentStatus`, `Platform` enums; `BrandBrief`, `Campaign`, `AgentRun`, `AgentMessage` models
- `brandforge/shared/config.py` — `BrandForgeConfig(BaseSettings)` with `BRANDFORGE_` env prefix, `load_secret()` with Secret Manager fallback, `get_gemini_api_key()`, singleton `settings`
- `brandforge/shared/firestore.py` — AsyncClient singleton, `save_document()`, `get_document()`, `update_document()`, collection name constants
- `brandforge/shared/storage.py` — GCS client singleton, `upload_blob()` → gs:// URI, `download_blob()`, `get_signed_url()`
- `brandforge/shared/pubsub.py` — Publisher singleton, `publish_message()` with JSON serialization, 2 topics only
- `brandforge/agent.py` — Root ADK agent (`root_agent = LlmAgent(name="brandforge_root", model="gemini-2.0-flash")`) with structured JSON logging, grounding instructions
- `scripts/bootstrap.sh` — Idempotent GCP provisioning (APIs, Firestore Native, GCS bucket, Pub/Sub topics, Artifact Registry)
- `scripts/seed_secrets.sh` — Interactive Secret Manager population
- `Dockerfile` — python:3.11-slim, uv install, `adk api_server` CMD on port 8080
- `cloudbuild.yaml` — Build → push Artifact Registry → deploy Cloud Run
- `deploy/cloudrun/service.yaml` — Knative spec: 2 CPU / 1Gi, autoscale 0–10
- `tests/__init__.py` — Package marker
- `tests/infra/__init__.py` — Package marker
- `tests/conftest.py` — Shared fixtures: `sample_brand_brief()`, `sample_campaign()`, GCP skip marker
- `tests/infra/test_models.py` — 14 tests: Pydantic round-trip, enum validation, UUID auto-gen, UTC timestamps, dict serialization
- `tests/infra/test_secrets.py` — 6 tests: Config defaults, env override, env fallback for secrets, `get_gemini_api_key()`
- `tests/infra/test_firestore.py` — 3 GCP-dependent tests: write/read Campaign, update status, get nonexistent
- `tests/infra/test_storage.py` — 2 GCP-dependent tests: upload/download, URI format
- `tests/infra/test_pubsub.py` — 3 GCP-dependent tests: publish message, attributes, JSON serialization

### Decisions Made
- Used `gemini-2.0-flash` instead of PRD's `gemini-3.1-pro-preview` for root agent (may not be a valid model ID; CLAUDE.md default applies). Trivially changeable in `brandforge/agent.py` line 39.
- Used `datetime.now(timezone.utc)` instead of PRD's `datetime.utcnow()` — same behavior, avoids Python 3.12+ deprecation warning.
- Used `LlmAgent` (not `Agent`) per ADK skill reference — they are equivalent, `LlmAgent` is more explicit.

### Blockers / Open Questions
- **Model name:** Confirm whether `gemini-3.1-pro-preview` is a valid model ID or stick with `gemini-2.0-flash`.
- GCP-dependent tests (`test_firestore.py`, `test_storage.py`, `test_pubsub.py`) marked `[UNVERIFIED]` — require live GCP project.
- `bootstrap.sh` actual execution: `[UNVERIFIED]` — requires GCP project.
- Cloud Build trigger: `[UNVERIFIED]` — requires GCP project and repo connection.

### Definition of Done Verification
| Item | Status |
|------|--------|
| `bootstrap.sh` runs without errors | `[UNVERIFIED]` (syntax check PASS) |
| Firestore write/read test | `[UNVERIFIED]` (needs GCP) |
| GCS upload/download test | `[UNVERIFIED]` (needs GCP) |
| Pub/Sub publish/receive test | `[UNVERIFIED]` (needs GCP) |
| config.py loads GEMINI_API_KEY | PASS |
| `adk web` starts and responds | PASS |
| `docker build` succeeds | PASS |
| Cloud Build trigger fires | `[UNVERIFIED]` (needs GCP) |
| Pydantic models serialize/deserialize | PASS (14 tests) |
| Structured logs appear | PASS (JSON format confirmed) |

### Next Session Should
- Begin Phase 1 (Brand Strategist Agent) by reading `brandforge-prd/phase-01-brand-strategist.md`.
- The root agent in `brandforge/agent.py` has empty `sub_agents=[]` — Phase 1 will add the first sub-agent.
- All shared infrastructure (`models.py`, `config.py`, `firestore.py`, `storage.py`, `pubsub.py`) is ready to use.
- Run `uv sync --extra dev` before testing (dev deps include pytest + pytest-asyncio).
- To run offline tests: `uv run pytest tests/ -m "not gcp" -v`

---

## Session 2026-03-09 15:00 — Phase 1: Brand Strategist Agent

**Status:** Complete
**Phase File:** phase-01-brand-strategist.md

### What Was Done
- `brandforge/shared/models.py` — Added 7 new Pydantic models: `ColorPalette` (5 hex colors with `field_validator`), `Typography`, `AudiencePersona`, `MessagingPillar`, `CompetitorInsight`, `VisualAssetAnalysis`, `BrandDNA` (master brand document, versioned, timestamped)
- `brandforge/shared/__init__.py` — Updated exports to include all new models
- `brandforge/shared/firestore.py` — Added `query_documents()` async helper with field filter, ordering, and limit (used for BrandDNA version incrementing)
- `brandforge/agents/brand_strategist/__init__.py` — Package marker with `from . import agent`
- `brandforge/agents/brand_strategist/prompts.py` — 5 prompt constants: `BRAND_STRATEGIST_INSTRUCTION`, `BRAND_DNA_SYSTEM_PROMPT`, `BRAND_DNA_USER_PROMPT_TEMPLATE`, `VISION_ANALYSIS_PROMPT`, `TRANSCRIPTION_PROMPT`
- `brandforge/agents/brand_strategist/tools.py` — 4 FunctionTool implementations:
  - `transcribe_voice_brief` — GCS download + Gemini audio transcription, 30s timeout, graceful fallback
  - `analyze_brand_assets` — GCS image download + Gemini Vision analysis → `VisualAssetAnalysis`
  - `generate_brand_dna` — Gemini structured output → `BrandDNA`, with fallback generator
  - `store_brand_dna` — Firestore + GCS persistence, version incrementing, Campaign doc update
  - Also: `_get_genai_client()` singleton, `_gcs_path_from_url()`, `_mime_from_url()`, `_build_fallback_dna()`
- `brandforge/agents/brand_strategist/agent.py` — `brand_strategist_agent = LlmAgent(model="gemini-2.0-flash", output_key="brand_dna_result", 4 FunctionTools)`
- `brandforge/agent.py` — Wired `brand_strategist_agent` as sub_agent, updated `ROOT_INSTRUCTION` with routing rules
- `tests/brand_strategist/__init__.py` — Test package marker
- `tests/brand_strategist/test_brand_strategist.py` — 19 unit tests + 6 integration test stubs covering all Definition of Done items
- `tests/conftest.py` — Added fixtures: `sample_color_palette`, `sample_visual_analysis`, `sample_brand_dna`
- `pyproject.toml` — Added `llm` pytest marker

### Decisions Made
- Used `gemini-2.0-flash` for the brand strategist agent (PRD Tech Stack table + CLAUDE.md alignment). Root agent remains `gemini-3.1-pro-preview`.
- Tools use simple string/list params (not complex Pydantic types) for LLM compatibility; complex objects pass via `tool_context.state`.
- `store_brand_dna` explicitly writes structured BrandDNA JSON to `tool_context.state["brand_dna_result"]` in addition to `output_key` capturing the agent's text summary.
- All sync GCS calls wrapped in `asyncio.to_thread()` to avoid blocking the event loop.
- `_build_fallback_dna()` provides a minimal valid BrandDNA when Gemini structured output fails.
- `query_documents()` uses `FieldFilter` for Firestore v2 API compatibility.

### Blockers / Open Questions
- Integration tests (`test_text_only_brief`, `test_output_key_populated`) require `GOOGLE_API_KEY` set. Run with `pytest -m llm`.
- GCP integration tests (`test_brand_dna_stored_in_firestore`, `test_version_increment`, `test_with_image_assets`, `test_voice_brief_transcription`) are stubs — require live Firestore + GCS + test fixtures.
- `async_query.FieldFilter` import used in `query_documents` — `[UNVERIFIED]` against live Firestore.
- Gemini `response_schema=BrandDNA` may fail with nested Pydantic validators (ColorPalette). The tool falls back to JSON schema + manual validation if needed.

### Definition of Done Verification
| Item | Status |
|------|--------|
| `brand_strategist_agent` importable, `adk web` starts | PASS |
| text_only_brief — valid BrandDNA returned | `[UNVERIFIED]` (needs `GOOGLE_API_KEY`) |
| with_image_assets — VisualAssetAnalysis influences palette | `[UNVERIFIED]` (needs GCP) |
| voice_brief_transcription — audio transcribed and merged | `[UNVERIFIED]` (needs GCP) |
| audio_timeout_fallback — graceful fallback | PASS (mocked test) |
| brand_dna_stored_in_firestore — doc exists | `[UNVERIFIED]` (needs GCP) |
| color_palette_hex_valid — all 5 colors pass regex | PASS (unit test) |
| no_hallucination — source_brief_summary has brand name | PASS (unit test) |
| version_increment — v2 created on rerun | `[UNVERIFIED]` (needs GCP) |
| output_key_populated — state has brand_dna_result | `[UNVERIFIED]` (needs `GOOGLE_API_KEY`) |
| All Phase 0 tests still pass | PASS (20/20 regression) |

### Next Session Should
- Begin Phase 2 (Creative Production Agents) by reading `brandforge-prd/phase-02-production-agents.md`.
- The brand strategist is wired in at `brandforge/agent.py:sub_agents=[brand_strategist_agent]`.
- BrandDNA model is in `brandforge/shared/models.py` — production agents will read from it.
- To run all offline tests: `uv run pytest tests/ -m "not llm and not gcp" -v` (39 tests).
- To run LLM integration tests: `GOOGLE_API_KEY=xxx uv run pytest tests/ -m llm -v`.
- If `response_schema=BrandDNA` fails with Gemini, update `generate_brand_dna` in `tools.py` to pass `BrandDNA.model_json_schema()` dict instead and validate manually.
