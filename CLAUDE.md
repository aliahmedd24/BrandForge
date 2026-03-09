# CLAUDE.md — BrandForge Agent Rules & Instructions

> This file governs all Claude Code sessions on the BrandForge project.
> Read this file completely before taking any action in a session.

---

## 1. Session Logging (Mandatory)

After **every session**, you must update `LOG.md` in the project root.

If `LOG.md` does not exist, create it with the structure below before writing.

### LOG.md Entry Format

```markdown
## Session [YYYY-MM-DD HH:MM] — Phase [X]: [Short Title]

**Status:** [In Progress | Complete | Blocked]
**Phase File:** phase-0X-[name].md

### What Was Done
- Bullet list of every file created or modified
- Include full relative paths

### Decisions Made
- Any architectural or implementation decision that deviated from the PRD
- Reason for the deviation

### Blockers / Open Questions
- Anything that requires human input before proceeding
- Any API, credential, or environment issue encountered

### Next Session Should
- The exact first task to pick up in the next session
- Any context needed to resume without re-reading everything
```

### Rules for the Log
- Never delete previous log entries — append only.
- Keep entries factual and terse — no padding.
- If a session produces zero code changes (e.g. planning only), still write a log entry marked `[Planning]`.
- The "Next Session Should" section is the most important — write it as if briefing a different agent that has no memory of this session.

---

## 2. Project Identity

**Project Name:** BrandForge  
**Type:** Multi-agent AI marketing platform  
**Hackathon Category:** Creative Storyteller (Google Gemini / ADK)  
**PRD Location:** `brandforge-prd/` directory  
**Primary PRD Index:** `brandforge-prd/README.md`

---

## 3. Phase Discipline

- Work **one phase at a time**. Never implement code from Phase N+1 while Phase N is incomplete.
- Before starting any phase, read its PRD file completely: `brandforge-prd/phase-0X-[name].md`.
- A phase is only **complete** when every item in its **Definition of Done** checklist passes.
- If a Definition of Done item cannot be verified (e.g. no test runner set up yet), mark it explicitly in `LOG.md` as `[UNVERIFIED]` — never silently skip it.
- If the PRD and a previous implementation decision conflict, **ask before proceeding**. Do not resolve ambiguity silently.

---

## 4. Technology Constraints (Non-Negotiable)

These cannot be changed without explicit human approval:

| Constraint | Rule |
|------------|------|
| Agent framework | **Google ADK only** — no raw `google.generativeai` SDK calls in agent logic |
| LLM model | `gemini-2.0-flash` for all agents unless PRD specifies otherwise |
| Agent hosting | **Cloud Run only** — no App Engine, no GKE, no Lambda |
| Database | **Firestore Native mode only** — no SQL, no Redis, no other NoSQL |
| Social posting | **MCP protocol only** — no direct REST calls to social APIs |
| Inter-agent messaging | **ADK A2A** (`RemoteA2aAgent` / `to_a2a()`) for cross-service agent calls; native ADK `ParallelAgent`/`LoopAgent` for agents within the same deployment; Pub/Sub for external event triggers only (`campaign.created`, `campaign.published`) |
| Secrets | **Secret Manager only** — never hardcode API keys, never use `.env` files in production |
| Schema validation | **Pydantic v2 only** — all data objects must be validated models |
| Python version | **3.11** — do not upgrade or downgrade |
| Package manager | **uv** — do not use pip directly |

---

## 5. File & Folder Conventions

```
brandforge/
├── CLAUDE.md                  ← This file
├── LOG.md                     ← Session log (auto-maintained by agent)
├── brandforge-prd/            ← PRD files (read-only — do not modify)
├── brandforge/
│   ├── agent.py               ← Root ADK agent entry point
│   ├── shared/
│   │   ├── models.py          ← ALL Pydantic schemas live here
│   │   ├── config.py          ← All config/secrets loading
│   │   ├── firestore.py       ← Firestore client singleton
│   │   ├── storage.py         ← GCS helpers
│   │   └── pubsub.py          ← Pub/Sub helpers
│   └── agents/
│       └── [agent_name]/
│           ├── agent.py       ← ADK LlmAgent definition
│           └── tools.py       ← FunctionTool implementations
├── tests/
│   ├── infra/                 ← Infrastructure tests (Phase 0)
│   └── [agent_name]/          ← Agent-specific tests
├── scripts/
│   ├── bootstrap.sh           ← GCP provisioning
│   └── seed_secrets.sh        ← Secret Manager population
├── deploy/
│   └── cloudrun/
│       └── service.yaml
├── Dockerfile
└── cloudbuild.yaml
```

**Rules:**
- All new Pydantic models go in `brandforge/shared/models.py` — never define schemas inside agent files.
- All new agents follow the `agents/[agent_name]/agent.py` + `tools.py` pattern — no exceptions.
- Test files mirror the source structure: `tests/brand_strategist/` for `agents/brand_strategist/`.
- Never modify files inside `brandforge-prd/` — those are spec files, not source files.

---

## 6. Code Quality Rules

- **Every function must have a docstring** — minimum one sentence describing what it does and what it returns.
- **Every async tool function must have a try/except** — catch specific exceptions, log them via `logging.error`, and either re-raise or return a typed error response. Never silently swallow exceptions.
- **No hardcoded strings** for things that may change — GCS bucket names, Firestore collection names, and Pub/Sub topic names (where still used) must come from `config.py`.
- **Type hints are mandatory** on all function signatures — input and return types.
- **No print statements** in production code — use `logging` with structured JSON format.

---

## 7. ADK-Specific Rules

**For all Google ADK coding conventions, patterns, and best practices, reference the `.agents\adk-skill` installed in this project.**

The skill covers agent types, tool design, callbacks, state management, MCP integration, A2A protocol (`RemoteA2aAgent` / `to_a2a()`), multi-agent orchestration, testing, evaluation, and deployment. Read the relevant skill reference file before writing any agent or tool code.
---


## 8. Before Ending Any Session

Run through this checklist mentally before writing the LOG.md entry:

- [ ] Does `adk web` start without errors?
- [ ] Do all new Pydantic models serialize/deserialize correctly?
- [ ] Are all new functions typed and docstrung?
- [ ] Are all secrets loaded from config, not hardcoded?
- [ ] Have relevant Definition of Done items been checked or marked `[UNVERIFIED]`?
- [ ] Is the LOG.md "Next Session Should" section specific enough for a cold-start agent?

---

## 9. When Stuck or Uncertain

**Stop and ask** rather than guessing. Specifically, always ask before:

- Changing any technology in the constraints table (Section 4).
- Modifying the shared `models.py` schemas in a breaking way.
- Skipping a Definition of Done item.
- Making an architectural decision not covered by the PRD.
- Spending more than 20 minutes on a single bug without resolution.

Write the blocker in `LOG.md` under "Blockers / Open Questions" and wait for human input.
