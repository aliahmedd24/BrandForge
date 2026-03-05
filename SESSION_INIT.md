# BrandForge — Session Initialization Protocol

## Session Initialization Protocol

Before beginning any work on this project, you MUST:

1. **Read CLAUDE.md** — This file contains all project rules, architecture guardrails, scope boundaries, and mandatory workflows
2. **Read LOG.md** — Review the latest session entries to understand current project state and recent decisions
3. **Identify Current Phase** — Determine which phase (0–8) you're working on from the last LOG.md entry
4. **Read Current Phase PRD** — Open the relevant `brandforge-prd/phase-0{N}-*.md` file for detailed specifications

---

## Session Start Checklist

Execute this checklist at the START of EVERY session:

```markdown
## Session Start: [YYYY-MM-DD HH:MM]

- [ ] Read CLAUDE.md completely
- [ ] Reviewed LOG.md — last 3 sessions minimum
- [ ] Identified current phase: Phase [N]
- [ ] Opened brandforge-prd/phase-0{N}-*.md for reference
- [ ] Reviewed "Definition of Done" for current phase
- [ ] Checked for any blockers from previous session
- [ ] Confirmed working in correct git branch (phase-{N}/*)
- [ ] If writing any agent, tool, or ADK code today → opened MEMORY.md before starting
```

---

## Core Directives

### 1. MANDATORY: Reference CLAUDE.md First

**EVERY session starts with:**
```
I have read CLAUDE.md and understand:
- Mandatory LOG.md update requirements
- Phase containment rules (no building ahead)
- Architecture guardrails (ADK agents, Pub/Sub A2A, Firestore, MCP only for social)
- Code standards (async, typed, Pydantic v2, structured logging)
- Testing requirements per phase PRD
- Git conventions (phase-{N}/feature-name branches)
- MEMORY.md is the ADK reference — I will read the relevant section before writing any agent or tool

Current Phase: [Phase N — Feature Name]
Current Objective: [Brief description from PRD]
```

### 2. MANDATORY: Update LOG.md at Session End

Before ending ANY session, you MUST update LOG.md with the exact format from CLAUDE.md:
- Session timestamp and phase
- Focus (one-line summary)
- Branch name
- Work completed (checklist format)
- Changed files (path + what/why)
- Decisions made
- Blockers / open issues
- Next steps for next session

**Failure to update LOG.md is a critical violation of project rules.**

### 3. MANDATORY: Phase Containment

Before implementing ANY feature, verify it belongs to the current phase:

| Phase | File | Scope |
|-------|------|-------|
| 0 | `phase-00-foundation.md` | GCP scaffold, ADK setup, Firestore, Pub/Sub, shared Pydantic schemas |
| 1 | `phase-01-brand-strategist.md` | Brand DNA generation, voice/vision brief ingestion, Firestore persistence |
| 2 | `phase-02-production-agents.md` | Scriptwriter, Mood Board, Image Gen (Imagen 4.0 Ultra), Video Producer (Veo 3.1), Virtual Try-On, Copy Editor |
| 3 | `phase-03-qa-assembler.md` | Multimodal QA scoring, regeneration loop, Campaign Assembler, brand kit PDF |
| 4 | `phase-04-live-canvas-ui.md` | React Live Canvas, Firestore real-time listeners, SSE streaming, voice recorder |
| 5 | `phase-05-distribution-pipeline.md` | Format Optimizer, Post Scheduler, MCP Social Publisher, OAuth flows |
| 6 | `phase-06-analytics-a2a.md` | Analytics Agent, BigQuery, A2A Pub/Sub feedback loop |
| 7 | `phase-07-advanced-intelligence.md` | Trend Injector, Competitor Intel, Brand Memory, Sage Voice Persona |
| 8 | `phase-08-demo-hardening.md` | Demo mode, infra panel, QA failure engineering, submission package |

```
✅ CORRECT: Building a feature listed in the current phase PRD
❌ WRONG: Building the MCP Publisher (Phase 5) while working in Phase 2
```

If a task crosses phase boundaries, implement ONLY what the current phase requires and note the forward dependency in LOG.md.

### 4. MANDATORY: Architecture Compliance

Before committing ANY code, verify these guardrails:

```python
# All agents must be ADK LlmAgent instances — never raw Gemini SDK
✅ CORRECT:
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

brand_strategist_agent = LlmAgent(
    name="brand_strategist",
    model="gemini-3.1-pro-preview",
    tools=[FunctionTool(analyze_brand_assets)],
)

❌ WRONG:
import google.generativeai as genai
model = genai.GenerativeModel("gemini-3.1-pro-preview")  # Never bypass ADK in agent code


# All inter-agent communication via Pub/Sub — no direct HTTP calls between agents
✅ CORRECT:
await pubsub_client.publish(
    topic="brandforge.agent.complete",
    message=AgentMessage(
        source_agent="brand_strategist",
        event_type="brand_dna_ready",
        campaign_id=campaign_id,
        payload={"brand_dna_id": brand_dna.id},
    )
)

❌ WRONG:
response = await httpx.post("http://scriptwriter-service/run", json=payload)  # Never


# All social posting through MCP — no direct platform REST calls
✅ CORRECT:
result = await mcp_client.call_tool(
    "instagram_post",
    {"image_url": gcs_signed_url, "caption": copy.caption}
)

❌ WRONG:
response = requests.post("https://graph.instagram.com/me/media", ...)  # Never


# All secrets from Secret Manager — never hardcoded or from .env in production
✅ CORRECT:
from brandforge.shared.config import get_secret
api_key = await get_secret("GEMINI_API_KEY")

❌ WRONG:
GEMINI_API_KEY = "AIzaSy..."  # Critical violation


# All Pydantic schemas in shared/models.py — never defined inside agent files
✅ CORRECT:
from brandforge.shared.models import BrandDNA, Campaign, AgentMessage

❌ WRONG:
# Inside agents/brand_strategist/agent.py:
class BrandDNA(BaseModel):  # Move this to shared/models.py immediately
    brand_name: str


# All agent tools must use FunctionTool wrapper
✅ CORRECT:
tools=[FunctionTool(transcribe_voice_brief), FunctionTool(analyze_brand_assets)]

❌ WRONG:
tools=[transcribe_voice_brief]  # Raw callable — not ADK compliant


# Business logic in tools.py — agent.py stays thin
✅ CORRECT:
# agents/brand_strategist/agent.py — LlmAgent definition and instruction prompt only
# agents/brand_strategist/tools.py — all Firestore, GCS, API implementation

❌ WRONG:
# 200 lines of Firestore queries and Gemini calls directly inside agent.py


# Agents are stateless — all state lives in Firestore, not in agent instances
✅ CORRECT:
async def generate_brand_dna(brief: BrandBrief, campaign_id: str) -> BrandDNA:
    existing = await firestore.get(f"campaigns/{campaign_id}")
    ...

❌ WRONG:
class BrandStrategistAgent:
    def __init__(self):
        self.last_brief = None  # Agents never hold state between calls
```

### 5. MANDATORY: Scope Adherence

**IN SCOPE** (proceed with implementation):
- Features explicitly listed in the current phase PRD
- Tests specified in the phase's "Definition of Done"
- Bug fixes for existing implemented code
- Security improvements within current scope
- Performance optimizations within the current phase

**OUT OF SCOPE** (require explicit approval before proceeding):
- Features from a later phase
- Architecture changes not documented in CLAUDE.md
- New third-party Python packages (justify in LOG.md first)
- Refactoring code outside the current task's files
- Any social platform not in the `Platform` enum
- User authentication beyond Firebase anonymous auth
- Multi-tenancy, billing, or subscription logic
- Mobile native apps (iOS / Android)
- Custom LLM fine-tuning
- Any database other than Firestore + BigQuery

If unsure, **ASK** before implementing.

---

## Workflow by Session Type

### Session Type A: Feature Implementation

```
1. Read feature specification in current phase PRD
2. Check "Definition of Done" criteria for this feature
3. Plan implementation — outline files to create/modify if > 2 files
4. Get confirmation on plan before writing code
5. Implement in small, testable increments
6. Write tests alongside implementation (not after)
7. Run linters: ruff check . && mypy . (backend) or pnpm lint (frontend)
8. Verify all phase PRD Definition of Done tests pass
9. Update LOG.md
10. Mark feature as complete in LOG.md
```

### Session Type B: Bug Fix

```
1. Document the bug in LOG.md (observed vs expected behavior)
2. Write a failing test that reproduces the bug
3. Implement the fix
4. Verify fix does not break ADK architecture guardrails
5. Run full test suite: uv run pytest (backend) or pnpm test (frontend)
6. Update LOG.md with root cause and solution
```

### Session Type C: Phase Transition

```
1. Review "Definition of Done" for the completing phase
2. Verify ALL checklist items are complete — no partial phases
3. Run full test suite with coverage report
4. Check linting: ruff check . && mypy . (backend) + pnpm lint && pnpm build (frontend)
5. Create phase summary entry in LOG.md
6. Document any technical debt carried forward
7. Request explicit phase review/approval before proceeding
8. ONLY move to next phase after human confirmation
9. Read the new phase PRD in full before writing a single line of code
```

### Session Type D: Environment / Infrastructure Setup

```
1. Follow Phase 0 PRD specifications exactly
2. Verify bootstrap.sh provisions all GCP services without error
3. Verify adk web starts and root_agent responds to a test message
4. Verify Firestore, GCS, and Pub/Sub connections via infra tests
5. Test Secret Manager access: config.py loads GEMINI_API_KEY correctly
6. Verify docker build completes and Cloud Build trigger fires on main push
7. Document any deviations or environment issues in LOG.md
8. Create troubleshooting notes for future sessions
```

### Session Type E: Continuation ("Continue" or "Resume" command)

```
1. Read last LOG.md entry's "Next Session Should" section verbatim
2. Confirm the next task aloud before starting
3. Pick up exactly where the previous session ended
4. Follow Session Type A workflow from step 2 onward
```

---

## Quick Reference Commands

### Before Starting Work
```bash
# Check current project state
git status
git branch --show-current
tail -n 80 LOG.md

# Verify ADK is working
adk web  # Should start without errors

# Validate root agent
adk check-agent brandforge.agent:root_agent

# Check GCP connection
gcloud config get-value project
gcloud run services list
```

### During Development (Backend / Agents)
```bash
# Run all tests
cd brandforge && uv run pytest -v

# Run specific test file
uv run pytest tests/brand_strategist/test_brand_strategist.py -v

# Test coverage
uv run pytest --cov=brandforge --cov-report=term-missing

# Linting and type checking
uv run ruff check .
uv run mypy .

# ADK local dev server
adk web

# Validate all agents
adk check-agent brandforge.agent:root_agent
```

### During Development (Frontend — Phase 4+)
```bash
# Dev server
cd frontend && pnpm dev

# Linting and type checking
pnpm lint
pnpm build  # Catches TypeScript errors

# Tests
pnpm test
pnpm cypress run  # E2E tests
```

### GCP / Infrastructure
```bash
# Deploy to Cloud Run
gcloud run deploy brandforge --source . --region us-central1

# Check Firestore
gcloud firestore databases list

# Check Pub/Sub topics and subscriptions
gcloud pubsub topics list
gcloud pubsub subscriptions list

# Tail Cloud Logging
gcloud logging read "resource.type=cloud_run_revision" --limit=50 --format=json

# Check Secret Manager
gcloud secrets list
gcloud secrets versions access latest --secret="GEMINI_API_KEY"

# Check Cloud Scheduler jobs (Phase 5+)
gcloud scheduler jobs list
```

### Before Declaring Work Complete
```bash
# Full backend validation
cd brandforge
uv run ruff check .
uv run mypy .
uv run pytest -v

# Full frontend validation (Phase 4+)
cd frontend
pnpm lint
pnpm build
pnpm test

# ADK validation
adk check-agent brandforge.agent:root_agent
```

---

## Communication Templates

### Starting a Session
```
Starting BrandForge session.

✅ Read CLAUDE.md
✅ Reviewed LOG.md (last session: [date] — [one-line summary])
✅ Current Phase: Phase [N] — [Phase Name]
✅ Objective: [Brief description from PRD or LOG.md next steps]
✅ Branch: phase-[N]/[feature-name]

Ready to begin. Next task: [specific task from LOG.md "Next Session Should"]
```

### Ending a Session
```
Session complete. Updating LOG.md now.

Summary:
- Completed: [list of tasks finished this session]
- Tests: [N tests added — passing/failing status]
- Linting: [clean / issues found and resolved]
- Definition of Done items checked: [N/total for current phase]
- Next session: [specific next task]

LOG.md updated ✅
```

### Requesting Clarification
```
⚠️ Clarification needed — pausing work:

**Context**: [What I'm working on and which phase / PRD section]
**Question**: [Specific question]
**Impact**: [Why this blocks progress or risks an architecture violation]
**Options**: [If applicable, list alternatives with tradeoffs]

Waiting for input before proceeding.
```

### Flagging a Scope Issue
```
🚫 Scope check — potential phase violation:

**Requested**: [What was asked]
**Current Phase**: Phase [N]
**Belongs to**: Phase [M] per brandforge-prd/phase-0{M}-*.md
**Recommendation**: [Defer to Phase M / implement minimally / proceed with explicit approval]

Awaiting decision before writing any code.
```

### Flagging an Architecture Violation Risk
```
⚠️ Architecture guardrail — pausing:

**Action I was about to take**: [e.g. "Call Instagram API directly from Publisher Agent"]
**Rule violated**: [e.g. "Social posting must use MCP protocol — CLAUDE.md Section 4"]
**Compliant alternative**: [e.g. "Use mcp_client.call_tool('instagram_post', ...) instead"]

Proceeding with compliant alternative unless instructed otherwise.
```

---

## Critical Reminders

### Architecture (Non-Negotiable)
- ✅ All agents are `LlmAgent` instances built with Google ADK — never raw Gemini SDK
- ✅ All agent tools use `FunctionTool` wrapper — no raw callables or decorators
- ✅ All inter-agent communication via Pub/Sub — no direct HTTP agent-to-agent calls
- ✅ All social posting via MCP protocol — no direct platform REST calls
- ✅ All secrets via Secret Manager — never `.env` files in production, never hardcoded
- ✅ All Pydantic schemas in `brandforge/shared/models.py` — never inside agent files
- ✅ All business logic in `tools.py` — `agent.py` contains only the `LlmAgent` definition
- ✅ All agents hosted on Cloud Run — no App Engine, no GKE
- ✅ Agents are stateless — all campaign state lives in Firestore, never in agent instances
- ✅ Analytics data in BigQuery — not Firestore
- ✅ All file assets in GCS — never local filesystem in Cloud Run containers
- ✅ Root agent always exported as `root_agent` from `brandforge/agent.py`

### ADK Coding Reference — MEMORY.md (Non-Negotiable)
- ✅ **Read MEMORY.md before writing any agent, tool, callback, or ADK integration**
- ✅ Section 3 before defining any `LlmAgent`
- ✅ Section 4 before using `ParallelAgent` (race conditions) or `LoopAgent` (exit pattern)
- ✅ Section 6 before writing any tool function (naming, docstring, return shape)
- ✅ Section 7 before wiring any MCP server (`McpToolset`, `tool_filter`)
- ✅ Section 10 before touching session state (scope prefixes, correct mutation path)
- ✅ Section 16 before sending images, audio, or video to any agent
- ✅ Section 17 before implementing Sage voice (`run_live`, `LiveRequestQueue`)
- ✅ Section 18 before designing any multi-agent topology
- ✅ Section 26 when hitting a runtime error — check anti-patterns first

### Agent Instruction Prompts (Non-Negotiable)
- ✅ Every agent instruction includes grounding: "Base all outputs strictly on the provided inputs"
- ✅ Every agent instruction includes an explicit "IMPORTANT: Do NOT" violations list
- ✅ Every agent instruction specifies the exact tool call sequence
- ✅ Gemini structured output (`response_schema`) must be used when the agent returns complex objects

### Security (Non-Negotiable)
- ✅ Firebase anonymous auth on all frontend → backend calls
- ✅ Campaigns are user-scoped — never expose another user's campaign data
- ✅ All user inputs validated via Pydantic before any processing
- ✅ No secrets in code, git commits, or Cloud Logging output
- ✅ Error responses must never expose internal stack traces or service names
- ✅ GCS bucket is private — all frontend asset access via signed URLs only

### Code Quality (Enforced)
- ✅ Type hints on every function — parameters and return types, no bare `Any`
- ✅ Docstring on every function — minimum one sentence describing inputs and outputs
- ✅ No `print()` statements — use `logging` with structured JSON format
- ✅ No `*` imports — always import specific names
- ✅ No function exceeding 50 lines — decompose into smaller functions
- ✅ No file exceeding 300 lines — refactor into submodules
- ✅ Config values (bucket names, topic names, collection names) from `config.py` — never inline strings
- ✅ `ruff check .` and `mypy .` clean before any commit

### Testing (Per Phase PRD)
- ✅ Every new agent tool gets at least one happy-path and one failure/fallback test
- ✅ External APIs (Gemini, Imagen, Veo, MCP) are mocked in unit tests — never hit real APIs in tests
- ✅ Tests named: `test_<what>_<condition>_<expected_result>`
- ✅ Full test suite passes before marking any task complete
- ✅ Phase "Definition of Done" checklist items are required — not optional

---

## Error Recovery Protocol

### ADK / Agent Startup Errors
```
1. Document error in LOG.md with full traceback
2. Run: adk check-agent brandforge.agent:root_agent
3. Verify root_agent is exported from brandforge/agent.py
4. Verify all sub_agents are importable and valid LlmAgent instances
5. Verify all FunctionTool functions have correct async signatures and type hints
6. Consult Phase 0 PRD for expected ADK configuration
7. If unresolvable in 20 minutes, document in LOG.md Blockers section and stop
```

### GCP / Infrastructure Errors
```
1. Document error in LOG.md
2. Verify GCP project is set: gcloud config get-value project
3. Check service account permissions: Cloud Run, Firestore, GCS, Pub/Sub, Secret Manager
4. Verify all secrets exist: gcloud secrets list
5. Check Cloud Run logs: gcloud logging read "resource.type=cloud_run_revision"
6. Re-run bootstrap.sh if provisioning state is uncertain
7. Document resolution steps in LOG.md for future sessions
```

### Test Failures
```
1. STOP — do not proceed with new features while tests are failing
2. Document failing tests in LOG.md with full assertion output
3. Fix failing tests before any new work begins
4. Verify the fix does not introduce architecture guardrail violations
5. Re-run full test suite to confirm clean pass
6. Only then resume feature work
```

### Scope Confusion
```
1. Stop work immediately
2. Re-read CLAUDE.md Section 8 (Out of Scope list)
3. Check whether the feature is in the current phase PRD
4. If not found, identify which phase PRD it belongs to
5. Document the question in LOG.md Blockers section
6. Ask for clarification — never guess on scope
```

### Veo / Imagen API Errors
```
1. Check Vertex AI quota limits in GCP Console
2. Verify model IDs match PRD: imagen-4.0-ultra-generate-001 (Imagen 4.0 Ultra), veo-3.1-generate-preview (Veo 3.1), virtual-try-on-001 (Virtual Try-On)
3. Verify Imagen prompts are under 480 tokens
4. For Veo: confirm async polling is implemented (30s intervals, 10-minute max timeout)
5. Test with a minimal 1-sentence prompt before the full campaign prompt
6. If API unavailable: document in LOG.md, use cached demo assets as fallback
```

### MCP Connection Errors
```
1. Verify MCP server URLs are correct per Phase 5 PRD configuration
2. Check OAuth token validity in Secret Manager
3. Test MCP connection independently before running the full Publisher agent
4. If one platform's MCP server is down, mark it unavailable — never block the full campaign
5. Document the failure in LOG.md — platform-level failures are acceptable, total failures are not
```

---

## Phase-Specific Notes

**Phase 0 — Foundation**: Everything downstream depends on this. Get Firestore in Native mode (not Datastore), GCS bucket structure, and all 5 Pub/Sub topics provisioned before touching any agent code. The shared `models.py` schemas are the contract between all 11 agents — define them carefully and completely.

**Phase 1 — Brand Strategist**: The Brand DNA document is the creative source of truth for the entire system. Every downstream agent reads it. Version incrementing is critical — never overwrite v1 with v2. The 30-second voice brief timeout fallback must be bulletproof — Gemini Live API latency is unpredictable.

**Phase 2 — Production Agents**: Parallelism is the technical centerpiece. All 5 agents triggered simultaneously via Pub/Sub dispatch. The Orchestrator must track all 5 completion events before triggering Phase 3. Veo's async operation polling (30s intervals, 10-minute max) must handle timeouts, partial failures, and retries gracefully.

**Phase 3 — QA Inspector**: BrandForge's biggest judge differentiator. The QA failure and recovery moment must be visually real — Gemini Vision must actually analyze image content, not just metadata. The scoring rubric must be embedded verbatim in the agent instruction prompt. Max 2 regeneration attempts per asset — always set the escalation path.

**Phase 4 — Live Canvas UI**: The most important phase for judge scoring (40% Innovation criterion). Firestore `onSnapshot` listeners drive all real-time updates — never poll. SSE streams script text character-by-character from the backend. The QA violation card animation is the demo's climactic moment — invest time in the Framer Motion timing.

**Phase 5 — Distribution**: MCP protocol is mandatory — zero direct social API calls. OAuth token refresh must surface gracefully in the UI via a popup re-auth flow, not a silent failure. Cloud Scheduler job creation per `PostScheduleItem` is the proof of real scheduling infrastructure that judges will look for.

**Phase 6 — Analytics & A2A**: The `creative_recommendations` array in the A2A message must be structured enough for the Orchestrator to parse programmatically — not free text. BigQuery writes must be idempotent. This phase is what proves the system is self-improving, not just a one-shot generator.

**Phase 7 — Advanced Intelligence**: Trend Injector's Google Search grounding must include `source_url` on every `TrendSignal` — this is the hallucination prevention proof judges look for. Sage's voice must feel like a real creative director: short sentences, specific creative references, genuine authority. Barge-in must actually interrupt the current TTS audio stream — not just queue the next message.

**Phase 8 — Demo Hardening**: The Grounded brand is pre-decided — do not improvise. The QA failure must be engineered to fire reliably on the first image pass via an intentionally off-brief Imagen prompt, and recover cleanly on the second pass. The 5-minute demo timing is a hard constraint — every component must have a cached fallback path for API slowness.

---

## Final Checklist Before Declaring Any Task Complete

```markdown
- [ ] Feature matches current phase PRD specification exactly
- [ ] Code follows all CLAUDE.md architecture guardrails
- [ ] All new agents are LlmAgent instances with FunctionTool wrappers
- [ ] Type hints on all functions — no bare Any
- [ ] Docstrings on all functions
- [ ] Tests written and passing — matches PRD "Definition of Done"
- [ ] External APIs mocked in tests — no real API calls in test suite
- [ ] Linting clean: ruff check . && mypy . (backend) or pnpm lint && pnpm build (frontend)
- [ ] No hardcoded secrets, API keys, or credentials anywhere
- [ ] No print() statements — structured logging only
- [ ] No config strings hardcoded — all from config.py
- [ ] No Pydantic schemas defined inside agent files — all in shared/models.py
- [ ] Error handling implemented with typed fallback responses
- [ ] No out-of-scope features added
- [ ] No new dependencies added without justification in LOG.md
- [ ] LOG.md updated with full session details and "Next Session Should"
```

---

## Priority Stack (Tiebreaker)

When you must choose between competing concerns, prioritize in this order:

1. **Correctness** — Code works, tests pass, ADK agent validates clean
2. **Compliance** — Code follows CLAUDE.md rules and the active phase PRD
3. **Clarity** — Code is readable, typed, documented, and structured
4. **Completeness** — All "Definition of Done" items are met
5. **Communication** — The human always knows exactly what you are doing and why

---

## How to Use This Prompt

**Copy and paste this entire document** into Claude Code at the start of EVERY session. This ensures:

1. Consistent adherence to project rules via CLAUDE.md
2. Proper session continuity via LOG.md
3. Phase discipline — no building ahead, no scope drift
4. Architecture compliance — ADK agents, Pub/Sub A2A, MCP social posting, Firestore state
5. Quality standards — typed, linted, tested, documented

**Remember**: BrandForge is a hackathon submission competing on Innovation (40%), Technical Architecture (30%), and Demo quality (30%). Every session must move the project toward a flawless, visually dramatic, technically airtight 5-minute demo. The code must be production-grade, the architecture must be sound, and every session must leave the project in a better, documented state than it started.

---

**Current Project Status**: [To be filled by reviewing LOG.md]  
**Current Phase**: [To be determined from LOG.md]  
**Next Task**: [To be identified from LOG.md "Next Session Should" or Phase 0 PRD if first session]

BEGIN SESSION.