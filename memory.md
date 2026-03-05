# BrandForge — MEMORY.md: Google ADK Complete Reference

> **Last Updated:** 2026-03-03  
> **Sources:** Google ADK official docs, Google Cloud Blog, Google Codelabs, Cloud NEXT 2025, Google Developers Blog  
> **Purpose:** Persistent reference for every Claude Code session. Read relevant sections before implementing any agent.  
> **Install:** `pip install google-adk` · **Docs:** [google.github.io/adk-docs](https://google.github.io/adk-docs)

---

## Table of Contents

1. [Core Philosophy & Golden Rules](#1-core-philosophy--golden-rules)
2. [Agent Types — When to Use Each](#2-agent-types--when-to-use-each)
3. [LlmAgent — Complete Reference](#3-llmagent--complete-reference)
4. [Workflow Agents](#4-workflow-agents)
5. [Custom Agents — Extending BaseAgent](#5-custom-agents--extending-baseagent)
6. [Tool Design — Complete Reference](#6-tool-design--complete-reference)
7. [MCP Integration — McpToolset](#7-mcp-integration--mcptoolset)
8. [Built-In Tools](#8-built-in-tools)
9. [AgentTool — Agents as Tools](#9-agenttool--agents-as-tools)
10. [Session State — Scoping, Mutations & Templates](#10-session-state--scoping-mutations--templates)
11. [Artifacts — Versioned Binary Data](#11-artifacts--versioned-binary-data)
12. [Memory Service — Long-Term Recall](#12-memory-service--long-term-recall)
13. [Callbacks — Intercept & Control](#13-callbacks--intercept--control)
14. [Structured I/O with Pydantic](#14-structured-io-with-pydantic)
15. [Runner & Session Bootstrap](#15-runner--session-bootstrap)
16. [Multimodal Content — Images, Audio, Video](#16-multimodal-content--images-audio-video)
17. [Live Bidirectional Streaming — run_live](#17-live-bidirectional-streaming--run_live)
18. [The 8 Multi-Agent Design Patterns](#18-the-8-multi-agent-design-patterns)
19. [Agent Transfer, Handoff & Escalation](#19-agent-transfer-handoff--escalation)
20. [Long-Running & Streaming Tools](#20-long-running--streaming-tools)
21. [Evaluation & Debugging](#21-evaluation--debugging)
22. [Deployment — Cloud Run & Vertex AI Agent Engine](#22-deployment--cloud-run--vertex-ai-agent-engine)
23. [Security Guidelines](#23-security-guidelines)
24. [Performance Optimization](#24-performance-optimization)
25. [BrandForge-Specific Patterns](#25-brandforge-specific-patterns)
26. [Common Mistakes & Anti-Patterns](#26-common-mistakes--anti-patterns)
27. [Quick Reference Cheatsheet](#27-quick-reference-cheatsheet)

---

## 1. Core Philosophy & Golden Rules

ADK was built on one principle: **agent development should feel like software development** — version-controlled, testable, modular, deployable like any other application. Google products like Agentspace and Customer Engagement Suite are themselves powered by ADK.

### The Three Golden Rules

**Rule 1 — Design Tools Like APIs**
- Name every tool with a clear **verb-noun pair**: `fetch_brand_dna`, `store_qa_result`, `publish_campaign_event`
- Write **rich docstrings** — the LLM reads name + docstring + type hints to decide *when* and *how* to call each tool. Poor docstrings = wrong tool calls.
- Every tool returns a **consistent shape**: `{"status": "success", "data": ...}` or `{"status": "error", "error": "..."}`
- Every tool implements: timeout handling, retry logic, and a graceful fallback

**Rule 2 — Compose, Don't Monolith**
- A single overloaded agent becomes "Jack of all trades, master of none" — as instructions grow, adherence degrades and hallucinations compound
- Treat each agent like a microservice: **one responsibility, one specialty**
- Use `SequentialAgent`, `ParallelAgent`, `LoopAgent` for deterministic pipelines
- Use `LlmAgent` with `sub_agents` for dynamic routing
- Modularity enables: simpler debugging, independent testing, reuse across workflows

**Rule 3 — State Is Sacred — Keep It Deterministic**
- Update session state exclusively via ADK's Event system (through `ToolContext` or `CallbackContext`) — never by direct mutation on a retrieved `Session` object
- Use `output_key` to auto-persist an agent's final response into session state
- Use ADK state templates (`{key_name}`) to inject state values directly into agent instructions
- In `ParallelAgent`: each sub-agent must write to a **unique state key** to prevent race conditions — they share the same session state

---

## 2. Agent Types — When to Use Each

ADK provides three fundamental categories, all extending `BaseAgent`:

| Agent Type | Class | Decision Engine | Use When |
|---|---|---|---|
| **LLM Agent** | `LlmAgent` (alias: `Agent`) | Gemini / LLM | Reasoning, language tasks, dynamic tool use, routing |
| **Sequential** | `SequentialAgent` | Deterministic | Linear pipeline A → B → C, data flows one direction |
| **Parallel** | `ParallelAgent` | Deterministic | Independent tasks that can run concurrently (fan-out) |
| **Loop** | `LoopAgent` | Deterministic | Iterative refinement, retry until condition met |
| **Custom** | Extend `BaseAgent` | Your logic | Non-LLM logic, conditional branching, custom orchestration |

**Key insight:** Workflow agents (`Sequential`, `Parallel`, `Loop`) do **not** call an LLM — they are pure orchestrators. Embed `LlmAgent` instances as their sub-agents to add intelligence.

---

## 3. LlmAgent — Complete Reference

```python
from google.adk.agents import LlmAgent  # 'Agent' is an alias

brand_strategist_agent = LlmAgent(
    # --- Required ---
    name="brand_strategist",              # Unique snake_case. Never use "user".
    model="gemini-3.1-pro-preview",             # LLM model string

    # --- Strongly Recommended ---
    description=(
        "Analyzes brand briefs (text, images, audio) and produces a structured "
        "Brand DNA document used by all downstream creative agents."
    ),
    instruction="""You are a world-class brand strategist.
    Given a brand brief, produce a precise Brand DNA document.

    Steps:
    1. If voice_brief_url is present, call transcribe_voice_brief first.
    2. If uploaded_asset_urls are present, call analyze_brand_assets.
    3. Call generate_brand_dna with all inputs.
    4. Call store_brand_dna with the validated result.

    IMPORTANT: Ground every output strictly in the provided brief.
    Do NOT invent brand attributes not supported by the input.
    Do NOT skip steps. Do NOT call tools out of order.
    """,

    tools=[
        transcribe_voice_brief,
        analyze_brand_assets,
        generate_brand_dna,
        store_brand_dna,
    ],
    output_key="brand_dna_result",
    input_schema=BrandBriefInput,
    output_schema=BrandDNAOutput,         # ⚠️ Cannot use tools AND output_schema simultaneously
    sub_agents=[competitor_intel_agent],

    before_model_callback=screen_input,
    before_tool_callback=guard_tool_call,
    after_tool_callback=normalize_output,
)
```

### LlmAgent Parameter Reference

| Parameter | Required | Purpose |
|---|---|---|
| `name` | ✅ | Unique snake_case. Never `"user"`. |
| `model` | ✅ | e.g. `"gemini-3.1-pro-preview"`, `"gemini-2.5-flash"` |
| `description` | ⚬ | Critical for multi-agent routing — peers read this to decide when to delegate |
| `instruction` | ⚬ | System prompt. Include role, step sequence, constraints, DO NOT list. |
| `tools` | ⚬ | FunctionTools, AgentTools, McpToolsets |
| `output_key` | ⚬ | Session state key where final text response is auto-saved |
| `input_schema` | ⚬ | Pydantic model for structured input |
| `output_schema` | ⚬ | Pydantic model for structured JSON output. Mutually exclusive with `tools`. |
| `sub_agents` | ⚬ | Required targets for `transfer_to_agent` calls |
| `before_model_callback` | ⚬ | Runs before LLM call — input guardrail |
| `after_model_callback` | ⚬ | Runs after LLM call — output sanitizer |
| `before_tool_callback` | ⚬ | Runs before each tool — validator/cache |
| `after_tool_callback` | ⚬ | Runs after each tool — post-processor |

### Writing Effective Instruction Prompts

```python
instruction = """
## Role
You are [specific role with expertise level].

## Objective
[One clear sentence describing what success looks like.]

## Steps (execute in this exact order)
1. [First action — which tool to call first]
2. [Second action — what input to provide]
3. [Third action — how to assemble the output]

## Output Format
[Exact schema or format of what to return.]

## IMPORTANT — Do NOT:
- Invent data not present in the provided inputs
- Call tools out of the specified order
- Skip validation steps
- Return partial results without completing all steps
"""
```

**Every instruction prompt checklist:**
- [ ] Clear role and persona definition
- [ ] Explicit step-by-step tool call sequence
- [ ] Examples of desired output for complex schemas
- [ ] "IMPORTANT: Do NOT" section listing forbidden behaviors
- [ ] Grounding statement: "Base all outputs strictly on the provided inputs"
- [ ] Concise `description` field for multi-agent routing (1–2 sentences)

---

## 4. Workflow Agents

Workflow agents are **deterministic orchestrators** — they control execution flow without LLM reasoning.

### SequentialAgent — Assembly Line

```python
from google.adk.agents import SequentialAgent

production_pipeline = SequentialAgent(
    name="production_pipeline",
    description="Runs all production agents in sequence: script → images → video → copy",
    sub_agents=[
        scriptwriter_agent,
        image_generator_agent,
        video_producer_agent,
        copy_editor_agent,
    ],
)
```

**State sharing between sequential agents** — each agent writes to `output_key`, next reads via `{key}` template:

```python
scriptwriter_agent = LlmAgent(..., output_key="video_script")

video_producer_agent = LlmAgent(
    instruction="Use this script to generate the video: {video_script}"
)
```

**Drawbacks:** Inflexible (can't skip steps), cumulative latency (total time = sum of all agents).

---

### ParallelAgent — Fan-Out / Gather

```python
from google.adk.agents import ParallelAgent

parallel_production = ParallelAgent(
    name="parallel_production",
    description="Runs image gen, video production, and copy editing concurrently",
    sub_agents=[
        image_generator_agent,
        video_producer_agent,
        copy_editor_agent,
    ],
)
```

⚠️ **Critical — Race Condition Prevention:** Parallel sub-agents share session state. Each MUST write to a **unique key**:

```python
image_generator_agent = LlmAgent(..., output_key="generated_images")
video_producer_agent  = LlmAgent(..., output_key="generated_videos")
copy_editor_agent     = LlmAgent(..., output_key="approved_copy")
```

**Fan-out then gather** — use a downstream SequentialAgent stage to collect parallel outputs:

```python
full_pipeline = SequentialAgent(
    name="full_pipeline",
    sub_agents=[
        brand_strategist_agent,
        ParallelAgent(name="parallel_production", sub_agents=[...]),
        campaign_assembler_agent,   # Reads all parallel output_keys from state
    ]
)
```

---

### LoopAgent — Iterative Refinement

```python
from google.adk.agents import LoopAgent

qa_refinement_loop = LoopAgent(
    name="qa_refinement_loop",
    sub_agents=[
        image_generator_agent,
        qa_inspector_agent,
    ],
    max_iterations=3,   # Always set a safety limit
)
```

**Exiting a loop** — a tool sets `tool_context.actions.escalate = True`:

```python
def exit_loop_if_approved(qa_score: float, tool_context: ToolContext) -> dict:
    """Signals the LoopAgent to stop if QA score meets threshold."""
    if qa_score >= 0.80:
        tool_context.actions.escalate = True
        return {"status": "approved", "score": qa_score}
    return {"status": "retry", "score": qa_score}
```

**Generator-Critic pattern** — the gold standard for iterative quality:

```python
generator = LlmAgent(
    name="generator",
    instruction="Generate an image prompt. If you received {feedback}, fix it and try again.",
    output_key="draft_prompt",
)
critic = LlmAgent(
    name="critic",
    instruction="Review: {draft_prompt}. Output 'APPROVED' if on-brand, or specific feedback if not.",
    output_key="feedback",
    tools=[exit_loop_if_approved],
)
loop = LoopAgent(name="refinement_loop", sub_agents=[generator, critic], max_iterations=3)
```

---

### Combining Patterns

```python
# BrandForge full pipeline
brandforge_pipeline = SequentialAgent(
    name="brandforge_pipeline",
    sub_agents=[
        trend_injector_agent,
        brand_strategist_agent,
        ParallelAgent(
            name="parallel_production",
            sub_agents=[
                scriptwriter_agent,
                mood_board_director_agent,
                image_generator_agent,
                video_producer_agent,
                copy_editor_agent,
            ]
        ),
        qa_inspector_agent,
        campaign_assembler_agent,
    ]
)
```

---

## 5. Custom Agents — Extending BaseAgent

When built-in workflow agents are insufficient, extend BaseAgent for custom orchestration logic.

### Python Example

```python
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.invocations import InvocationContext
from typing import AsyncGenerator

class ConditionalQAAgent(BaseAgent):
    def __init__(self, qa_agent, regen_agent, threshold=0.80):
        super().__init__(
            name="conditional_qa_agent",
            description="Runs QA and conditionally regenerates assets below threshold.",
            sub_agents=[qa_agent, regen_agent],
        )
        self.qa_agent = qa_agent
        self.regen_agent = regen_agent
        self.threshold = threshold

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        async for event in self.qa_agent.run_async(ctx):
            yield event
        qa_score = ctx.session.state.get("qa_score", 0.0)
        if qa_score < self.threshold:
            async for event in self.regen_agent.run_async(ctx):
                yield event
```

**When to use Custom Agents:**
- Conditional branching based on runtime state values
- Complex retry logic with custom backoff strategy
- Non-LLM business rules (score thresholds, rule-based routing)
- Custom async orchestration not expressible with Sequential/Parallel/Loop

---

## 6. Tool Design — Complete Reference

### Auto-Wrapped FunctionTool

ADK auto-wraps plain functions. The LLM reads name + docstring + type hints to determine when/how to call each tool.

```python
async def fetch_brand_dna(campaign_id: str, version: int = 1) -> dict:
    """Fetches the Brand DNA document from Firestore.

    Args:
        campaign_id: The unique campaign identifier.
        version: Brand DNA version (default: latest).

    Returns:
        dict with status ("success"/"error"), data (BrandDNA dict), error (str).
    """
    try:
        doc = await firestore.get(f"brand_dna/{campaign_id}_v{version}")
        if not doc:
            return {"status": "error", "error": f"Not found: {campaign_id}"}
        return {"status": "success", "data": doc.to_dict()}
    except Exception as e:
        logging.error(f"fetch_brand_dna failed: {e}", extra={"campaign_id": campaign_id})
        return {"status": "error", "error": str(e)}
```

### Tool Design Checklist

- [ ] Descriptive verb-noun name (fetch_brand_dna, not get_data)
- [ ] Full docstring with Args: and Returns: sections
- [ ] Consistent return: {"status": "success/error", "data/error": ...}
- [ ] async def for all I/O-bound operations
- [ ] try/except with logging.error — never let exceptions crash the agent
- [ ] Timeout handling for external API calls
- [ ] Retry logic (max 3, exponential backoff) for transient failures
- [ ] Tested independently before wiring into an agent
- [ ] Only created when truly needed — avoid tool sprawl

### ToolContext Usage

```python
from google.adk.tools import ToolContext

async def store_brand_dna(brand_dna: dict, campaign_id: str, tool_context: ToolContext) -> dict:
    """Stores Brand DNA and updates session state."""
    brand_dna_id = brand_dna.get("id")
    await firestore.set(f"brand_dna/{brand_dna_id}", brand_dna)

    # Correct mutation — tracked by ADK event system
    tool_context.state["brand_dna_id"] = brand_dna_id
    tool_context.state["temp:last_op"] = "store_brand_dna"

    return {"status": "success", "brand_dna_id": brand_dna_id}
```

### ToolContext Properties

```python
tool_context.state                                       # Read/write session state
tool_context.actions.transfer_to_agent = "agent_name"  # Transfer to sub-agent
tool_context.actions.escalate = True                     # Stop agent / exit LoopAgent
tool_context.actions.skip_summarization = True           # Return result directly to user
await tool_context.save_artifact(filename, part)         # Save versioned binary artifact
await tool_context.load_artifact(filename, version)      # Load artifact by name+version
await tool_context.search_memory(query)                  # Query long-term memory service
tool_context.send_intermediate_result(data)              # Streaming: push partial result
```

---

## 7. MCP Integration — McpToolset

MCP is the standard for connecting agents to external services. BrandForge uses MCP exclusively for all social platform integrations — zero direct REST API calls to any platform.

```python
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, SseConnectionParams, StdioConnectionParams

# Remote MCP server via SSE (production services)
instagram_toolset = McpToolset(
    connection_params=SseConnectionParams(
        url="https://mcp.instagram.com/v1/sse",
        headers={"Authorization": f"Bearer {await get_secret('INSTAGRAM_TOKEN')}"},
    ),
    tool_filter=["post_image", "post_video", "get_post_metrics"],  # Only expose what's needed
)

# Local MCP server via stdio (dev / filesystem tools)
local_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/assets"],
        ),
    ),
    tool_filter=["read_file", "list_directory"],
)

social_publisher = LlmAgent(
    name="instagram_publisher",
    model="gemini-3.1-pro-preview",
    description="Posts content to Instagram via MCP and retrieves engagement metrics.",
    instruction="""Post the provided asset to Instagram.
    Use post_image for static images, post_video for videos.
    Always include the caption from the approved copy package.""",
    tools=[instagram_toolset],
)
```

**Always use `tool_filter`** — exposing all tools from a large MCP server wastes tokens on descriptions and increases incorrect tool selection.

### Exposing ADK Tools as an MCP Server

```python
from mcp.server.fastmcp import FastMCP

mcp_server = FastMCP("brandforge-tools")

@mcp_server.tool()
async def generate_brand_dna(brand_name: str, product_description: str) -> dict:
    """Generates a complete Brand DNA document. Callable by any MCP client."""
    result = await runner.run_async(user_id="system", session_id="mcp", new_message=...)
    return result
```

---

## 8. Built-In Tools

```python
from google.adk.tools import google_search, LoadArtifactsTool
from google.adk.tools.code_execution import BuiltInCodeExecutionTool

# Google Search — grounded, real-time web search
trend_injector_agent = LlmAgent(
    name="trend_injector",
    model="gemini-3.1-pro-preview",
    instruction="Search for trending content formats. Include source URLs for grounding proof.",
    tools=[google_search],
)

# Code Execution — Gemini writes and runs Python in a hermetic sandbox
analytics_agent = LlmAgent(
    name="analytics_agent",
    model="gemini-3.1-pro-preview",
    instruction="Compute engagement rate statistics from the provided metrics data.",
    tools=[BuiltInCodeExecutionTool()],
)

# Load Artifacts Tool — agent reads named artifacts by reference in instructions
qa_agent = LlmAgent(
    name="qa_inspector",
    model="gemini-3.1-pro-preview",
    instruction="Review the mood board at {artifact.mood_board.pdf} against the Brand DNA.",
    tools=[LoadArtifactsTool()],
)
```

---

## 9. AgentTool — Agents as Tools

Wrapping an agent as a tool gives the caller fine-grained control: invoke the specialist, get the result, and continue reasoning. Unlike `transfer_to_agent`, control stays with the orchestrator.

```python
from google.adk.tools import AgentTool

orchestrator = LlmAgent(
    name="campaign_orchestrator",
    model="gemini-3.1-pro-preview",
    instruction="""You are the campaign orchestrator.
    Step 1: Call brand_strategist_tool to generate Brand DNA.
    Step 2: Call qa_inspector_tool to validate all assets.
    Step 3: Call assemble_campaign to produce the final bundle.
    You retain control throughout — do not transfer.""",
    tools=[
        AgentTool(agent=brand_strategist_agent),
        AgentTool(agent=qa_inspector_agent),
        assemble_campaign,
    ],
)
```

| Mechanism | Control After Call | Use When |
|---|---|---|
| `AgentTool` | Stays with caller | Caller needs result to continue reasoning |
| `transfer_to_agent` | Moves to target | Specialist handles everything from here |
| LLM auto-delegation | Moves to sub-agent | Simple routing via description matching |

---

## 10. Session State — Scoping, Mutations & Templates

### State Scope Prefixes

```python
ctx.state["campaign_status"]           # Session-scoped — this session only
ctx.state["user:brand_preferences"]    # User-scoped — all sessions for this user
ctx.state["app:platform_rate_limits"]  # App-scoped — all users, all sessions
ctx.state["temp:raw_api_response"]     # Invocation-scoped — discarded after this turn
```

| Prefix | Scope | Persists? | Use For |
|---|---|---|---|
| (none) | Current session | Yes (with persistent SessionService) | Campaign workflow state |
| `user:` | All sessions, this user | Yes | Brand prefs, user settings |
| `app:` | All users, all sessions | Yes | Global config, rate limits |
| `temp:` | Current invocation only | Never | Scratch values, raw API responses |

### Correct State Mutations

```python
# Correct: via ToolContext inside a tool
async def save_brand_dna_id(brand_dna_id: str, tool_context: ToolContext) -> dict:
    tool_context.state["brand_dna_id"] = brand_dna_id
    return {"status": "success"}

# Correct: auto-save via output_key
scriptwriter_agent = LlmAgent(..., output_key="video_script")

# Correct: via CallbackContext in a callback
def before_agent_cb(callback_context):
    callback_context.state["session_start"] = datetime.utcnow().isoformat()

# WRONG: direct mutation bypasses event tracking — breaks persistence
session = await session_service.get_session(...)
session.state["key"] = "value"   # Never do this
```

### State Templates in Instructions

```python
video_producer_agent = LlmAgent(
    instruction="""Generate a video using this script: {video_script}
    Brand DNA palette: {brand_palette}
    Visual direction: {visual_direction?}
    If any values are empty, call fetch_missing_context first."""
    # {key}  = required, substituted from session.state["key"]
    # {key?} = optional, becomes empty string if key not found
)
```

---

## 11. Artifacts — Versioned Binary Data

Keep images, videos, PDFs, and audio files out of the LLM token context. Artifacts are named, versioned binary blobs managed by an ArtifactService.

```python
from google.adk.artifacts import GcsArtifactService
from google.adk.runners import Runner
from google.genai import types

artifact_service = GcsArtifactService(bucket_name="brandforge-assets")
runner = Runner(
    agent=root_agent,
    app_name="brandforge",
    session_service=session_service,
    artifact_service=artifact_service,
)
```

### Saving and Loading from Tools

```python
async def save_generated_image(image_bytes: bytes, filename: str, tool_context: ToolContext) -> dict:
    """Saves a generated image as a versioned artifact in GCS."""
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    version = await tool_context.save_artifact(filename, image_part)
    return {"status": "success", "filename": filename, "version": version}

async def load_generated_image(filename: str, version: int, tool_context: ToolContext) -> dict:
    """Loads a specific version of an image artifact."""
    artifact = await tool_context.load_artifact(filename, version=version)
    if artifact is None:
        return {"status": "error", "error": f"Not found: {filename} v{version}"}
    return {"status": "success", "data": artifact.inline_data.data}

# User-scoped artifacts persist across sessions
await tool_context.save_artifact("user:brand_logo.png", logo_part)
```

**State vs Artifacts:**

| Use State for | Use Artifacts for |
|---|---|
| Strings, numbers, IDs, flags | Images, videos, PDFs, audio files |
| Workflow coordination values | Generated creative assets |
| Config, timestamps, small dicts | Large documents, binary data |

---

## 12. Memory Service — Long-Term Recall

Memory lets agents recall information from past sessions — used in BrandForge's Brand Memory feature.

```python
from google.adk.memory import VertexAiMemoryBankService

memory_service = VertexAiMemoryBankService(project="brandforge-prod", location="us-central1")
runner = Runner(agent=root_agent, app_name="brandforge",
                session_service=session_service, memory_service=memory_service)
```

```python
async def recall_brand_history(brand_id: str, tool_context: ToolContext) -> dict:
    """Recalls past campaign performance insights from long-term memory."""
    results = await tool_context.search_memory(f"campaign performance for brand {brand_id}")
    if not results.memories:
        return {"status": "success", "memories": [], "message": "No prior campaigns"}
    memories = [m.content.parts[0].text for m in results.memories]
    return {"status": "success", "memories": memories}
```

| Tier | Service | Scope | Use For |
|---|---|---|---|
| Session state | `SessionService` | Current conversation | Campaign workflow, intermediate results |
| User state | `SessionService` (`user:`) | User across sessions | Brand prefs, tone settings |
| Long-term memory | `MemoryService` | Semantic search across history | Past performance, cross-campaign patterns |

---

## 13. Callbacks — Intercept & Control

```python
from google.adk.models import LlmResponse
from google.genai import types

# before_model_callback: input guardrail, runs before LLM call
def screen_for_injection(callback_context, llm_request):
    prompt = str(llm_request.contents).lower()
    if any(p in prompt for p in ["ignore previous instructions", "new persona"]):
        return LlmResponse(content=types.Content(
            role="model", parts=[types.Part(text='{"status": "error", "error": "Invalid input."}')]
        ))
    return None  # Allow LLM call

# before_tool_callback: gate / cache
def guard_qa_calls(tool, args, tool_context):
    asset_id = args.get("asset_id")
    if tool_context.state.get(f"qa_approved:{asset_id}"):
        return {"status": "cached", "qa_score": tool_context.state[f"qa_score:{asset_id}"]}
    return None  # Execute normally

# after_tool_callback: sanitize output
def redact_secrets(tool, args, tool_context, tool_result):
    if "access_token" in str(tool_result) or "client_secret" in str(tool_result):
        return {"status": "error", "error": "Sensitive data redacted."}
    return None  # Keep original

agent = LlmAgent(
    name="secure_agent", model="gemini-3.1-pro-preview", tools=[my_tool],
    before_model_callback=screen_for_injection,
    before_tool_callback=guard_qa_calls,
    after_tool_callback=redact_secrets,
)
```

| Callback | Return `None` | Return object |
|---|---|---|
| `before_agent_callback` | Run agent | Skip agent, use returned `Content` |
| `before_model_callback` | Call LLM | Skip LLM, use returned `LlmResponse` |
| `before_tool_callback` | Execute tool | Skip tool, use returned `dict` |
| `after_agent_callback` | Keep output | Replace with returned `Content` |
| `after_model_callback` | Keep response | Replace with returned `LlmResponse` |
| `after_tool_callback` | Keep result | Replace with returned `dict` |

---

## 14. Structured I/O with Pydantic

```python
from pydantic import BaseModel, Field

class BrandBriefInput(BaseModel):
    brand_name: str = Field(description="The brand name.")
    product_description: str = Field(description="What the product does.")
    target_audience: str = Field(description="Primary target audience.")
    tone_keywords: list[str] = Field(description="3-5 adjectives describing brand tone.")
    platforms: list[str] = Field(description="Target platforms: instagram, linkedin, tiktok, x.")

class BrandDNAOutput(BaseModel):
    brand_essence: str = Field(description="One-sentence brand soul.")
    brand_personality: list[str] = Field(description="Exactly 5 personality adjectives.")
    tone_of_voice: str = Field(description="Detailed tone paragraph.")
    primary_color: str = Field(description="Primary hex e.g. #C4894F")
    secondary_color: str = Field(description="Secondary hex.")
    core_message: str = Field(description="The single most important brand message.")

brand_strategist_agent = LlmAgent(
    model="gemini-3.1-pro-preview",
    name="brand_strategist",
    instruction="Analyze the brand brief and produce the Brand DNA.",
    input_schema=BrandBriefInput,
    output_schema=BrandDNAOutput,   # Cannot use tools= with output_schema on most models
    output_key="brand_dna_structured",
)
```

**`output_schema` + `tools` conflict workarounds:**
1. Use a dedicated schema-extraction agent (no tools) after the tool-using agent finishes
2. Inject JSON format requirement into `instruction` and parse the text output
3. Use `before_model_callback` to enforce JSON format via system instruction injection

---

## 15. Runner & Session Bootstrap

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, DatabaseSessionService
from google.adk.artifacts import GcsArtifactService
from google.adk.memory import VertexAiMemoryBankService
from google.genai import types

# Production setup
session_service  = DatabaseSessionService(db_url=await get_secret("DATABASE_URL"))
artifact_service = GcsArtifactService(bucket_name="brandforge-assets")
memory_service   = VertexAiMemoryBankService(project="brandforge-prod", location="us-central1")

runner = Runner(
    agent=root_agent,               # Must export as `root_agent` for `adk web`
    app_name="brandforge",
    session_service=session_service,
    artifact_service=artifact_service,
    memory_service=memory_service,
)

# Create session (seed with campaign context)
session = await session_service.create_session(
    app_name="brandforge",
    user_id=user_id,
    session_id=campaign_id,         # Use campaign_id as session_id for traceability
    state={"campaign_id": campaign_id, "user_id": user_id}
)

# Run the agent
user_message = types.Content(
    role="user",
    parts=[types.Part(text=json.dumps(brand_brief.model_dump()))]
)

async for event in runner.run_async(
    user_id=user_id,
    session_id=campaign_id,
    new_message=user_message,
):
    if event.is_final_response() and event.content and event.content.parts:
        final_text = event.content.parts[0].text
        logging.info("Final response", extra={"campaign_id": campaign_id})
```

### Vertex AI Agent Engine (Production Deployment)

```python
from vertexai.agent_engines import AdkApp

# AdkApp handles managed sessions automatically after deployment
app = AdkApp(agent=root_agent)

async for event in app.async_stream_query(
    user_id=user_id,
    message=brand_brief_json,
):
    process_event(event)
```

---

## 16. Multimodal Content — Images, Audio, Video

```python
from google.genai import types

# Sending an image
with open("brand_logo.png", "rb") as f:
    image_bytes = f.read()

user_message = types.Content(
    role="user",
    parts=[
        types.Part(text="Analyze this brand logo and extract color palette and typography style."),
        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
    ],
)

# Sending multiple images (competitor analysis)
parts = [types.Part(text="Analyze these competitor ads and identify differentiation opportunities.")]
for url in competitor_screenshot_urls:
    img_bytes = await download_from_gcs(url)
    parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

# Sending audio (voice brief)
with open("voice_brief.wav", "rb") as f:
    audio_bytes = f.read()

user_message = types.Content(
    role="user",
    parts=[
        types.Part(text="Transcribe and extract brand brief information from this audio."),
        types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
    ],
)

# Video QA — extract frames and send as images
import cv2

cap = cv2.VideoCapture("generated_ad.mp4")
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
positions = [0, 0.25, 0.50, 0.75, 1.0]  # 5 sample points

video_parts = [types.Part(text="Review these video frames against the Brand DNA. Score 0.0-1.0.")]
for pos in positions:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * pos))
    ret, frame = cap.read()
    if ret:
        _, buffer = cv2.imencode(".jpg", frame)
        video_parts.append(types.Part.from_bytes(data=buffer.tobytes(), mime_type="image/jpeg"))
cap.release()
```

**Model requirements:**

| Input Type | Minimum Model |
|---|---|
| Text only | Any Gemini |
| Images / Screenshots | `gemini-3.1-pro-preview`+ |
| Audio (non-live) | `gemini-3.1-pro-preview`+ |
| Video frames as images | `gemini-3.1-pro-preview`+ |
| Live bidirectional audio | `gemini-3.1-pro-preview` (Live API) |

---

## 17. Live Bidirectional Streaming — run_live

Used in BrandForge for the Sage Voice Persona — real-time voice with barge-in support.

```python
from google.adk.runners import Runner
from google.adk.streaming import LiveRequestQueue
from google.genai import types

sage_voice_agent = LlmAgent(
    name="sage_voice_orchestrator",
    model="gemini-3.1-pro-preview",           # Must support Live API
    instruction="""You are Sage, BrandForge's AI Creative Director.
    Personality: Confident, warm, precise. Short sentences. Specific language.
    When narrating: describe what you are doing and why, briefly.
    When receiving feedback: confirm, then act immediately.
    IMPORTANT: Never fabricate capabilities. State clearly what you can do instead.""",
    tools=[get_campaign_status, modify_generation_instruction],
)

# Create queue and configure run
live_request_queue = LiveRequestQueue()

run_config = types.RunConfig(
    response_modalities=["AUDIO", "TEXT"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Sage")
            # Options: Sage, Kore, Charon, Fenrir, Aoede, Puck
        )
    ),
)

# Start live session
live_events = runner.run_live(
    user_id=user_id,
    session_id=campaign_id,
    live_request_queue=live_request_queue,
    run_config=run_config,
)

# Send audio input (runs in separate coroutine)
async def send_audio_stream(audio_source):
    async for chunk in audio_source:
        live_request_queue.send_content(
            types.Content(role="user", parts=[
                types.Part.from_bytes(data=chunk, mime_type="audio/pcm;rate=16000")
            ])
        )
    live_request_queue.close()

# Process live events
async def process_live_events():
    async for event in live_events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    await ws.send_json({"type": "narration_text", "text": part.text})
                elif part.inline_data:
                    await ws.send_bytes(part.inline_data.data)  # Audio bytes

await asyncio.gather(send_audio_stream(mic_input), process_live_events())
```

> **Barge-in is automatic** — when the user starts speaking mid-response, Sage's current audio stops immediately. No additional code required.

### RunConfig Voice Options

```python
run_config = types.RunConfig(
    response_modalities=["AUDIO"],      # "TEXT" | "AUDIO" | ["TEXT", "AUDIO"]
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Sage"       # Sage, Kore, Charon, Fenrir, Aoede, Puck
            )
        )
    ),
)
```

---

## 18. The 8 Multi-Agent Design Patterns

These are Google's officially documented patterns for production multi-agent systems.

### Pattern 1 — Sequential Pipeline
Linear assembly line. Deterministic, easy to debug. Each agent passes output to the next.
```python
SequentialAgent(sub_agents=[parser, extractor, summarizer])
```

### Pattern 2 — Coordinator / Dispatcher
One central `LlmAgent` routes to specialist sub-agents via description-based auto-delegation.
```python
coordinator = LlmAgent(instruction="Route to specialists.", sub_agents=[billing_agent, support_agent])
# ADK AutoFlow reads sub-agent descriptions to decide who handles the request
```

### Pattern 3 — Parallel Fan-Out / Gather
`ParallelAgent` runs independent agents simultaneously. A downstream agent gathers results via state keys.
```python
ParallelAgent(sub_agents=[image_agent, video_agent, copy_agent])
# Each writes to unique output_key — race condition prevention is MANDATORY
```

### Pattern 4 — Generator / Critic (LoopAgent)
One agent generates, another critiques. Loops until pass condition or max_iterations.
```python
LoopAgent(sub_agents=[generator, critic], max_iterations=3)
# Critic calls exit_loop tool when output is approved
```

### Pattern 5 — Iterative Refinement
Similar to Pattern 4 but focused on qualitative improvement rather than binary pass/fail. Multiple passes with progressive enhancement.

### Pattern 6 — Hierarchical Delegation
Nested agent trees. Coordinators delegate to sub-coordinators, each managing specialists.
```python
root = LlmAgent(sub_agents=[
    SequentialAgent(name="strategy_team", sub_agents=[trend_agent, brand_agent]),
    ParallelAgent(name="production_team", sub_agents=[image_agent, video_agent, copy_agent]),
])
```

### Pattern 7 — Human-in-the-Loop
A tool pauses execution and sends an approval request to an external system (UI, Slack, ticket). Agent resumes when human responds.
```python
def request_human_approval(action: str, severity: str, tool_context: ToolContext) -> dict:
    """Pauses execution and sends approval request to human reviewer."""
    ticket_id = create_approval_ticket(action, severity)
    tool_context.state["pending_approval_ticket"] = ticket_id
    return {"status": "pending_approval", "ticket_id": ticket_id}
```

### Pattern 8 — Composite (Production Systems)
Combine all patterns as needed. Real enterprise systems rarely fit one pattern alone.

**BrandForge's full pattern:**
```
Root LlmAgent (Hierarchical Dispatcher)
  └── SequentialAgent (main campaign pipeline)
        ├── TrendInjector (LlmAgent + google_search)
        ├── BrandStrategist (LlmAgent + vision tools)
        ├── ParallelAgent (fan-out: Script + Mood + Images + Video + Copy)
        ├── LoopAgent (QA Inspector + Regeneration, max 2 iterations)
        ├── CampaignAssembler (LlmAgent)
        └── SequentialAgent (Format → Schedule → Publish via MCP)
Analytics A2A: Cloud Scheduler triggers Analytics Agent → Pub/Sub feedback → Root Agent
```

---

## 19. Agent Transfer, Handoff & Escalation

### Explicit Transfer via Tool

```python
from google.adk.tools import ToolContext

def route_to_brand_strategist(reason: str, tool_context: ToolContext) -> dict:
    """Transfers control to the Brand Strategist when a brief is ready."""
    tool_context.actions.transfer_to_agent = "brand_strategist"  # Must match agent `name`
    return {"status": "transferring", "reason": reason}

# Target must be listed in sub_agents
orchestrator = LlmAgent(
    name="orchestrator",
    tools=[route_to_brand_strategist],
    sub_agents=[brand_strategist_agent],  # Required — target must be registered here
)
```

### LLM Auto-Delegation via Description

```python
orchestrator = LlmAgent(
    name="orchestrator",
    instruction="Route requests to the appropriate specialist.",
    sub_agents=[
        LlmAgent(name="brand_strategist",  description="Analyzes brand briefs and creates Brand DNA."),
        LlmAgent(name="qa_inspector",      description="Reviews generated assets for brand alignment."),
        LlmAgent(name="social_publisher",  description="Posts approved campaign assets to social media."),
    ],
)
# ADK AutoFlow reads descriptions and delegates automatically
```

### Escalation — Stop and Bubble Up

```python
def escalate_qa_failure(asset_id: str, attempts: int, tool_context: ToolContext) -> dict:
    """Escalates QA failure to parent agent when max retries exceeded."""
    tool_context.actions.escalate = True  # Stops agent; exits LoopAgent if inside one
    return {"status": "escalated", "asset_id": asset_id, "attempts": attempts}
```

---

## 20. Long-Running & Streaming Tools

### Pattern A — Job ID + Status Poll (for Veo, Imagen)

```python
async def submit_veo_generation(script: dict, brand_dna: dict) -> dict:
    """Submits Veo 3.1 video generation. Returns operation_id for polling.

    Args:
        script: VideoScript with scene descriptions.
        brand_dna: Brand DNA for visual direction.

    Returns:
        dict with status and operation_id for use with check_veo_status.
    """
    prompt = build_veo_prompt(script, brand_dna)
    operation = await vertex_ai.generate_video(model="veo-3.1-generate-preview", prompt=prompt)
    return {"status": "started", "operation_id": operation.name}


async def check_veo_status(operation_id: str) -> dict:
    """Checks Veo generation operation status.

    Args:
        operation_id: The operation ID from submit_veo_generation.

    Returns:
        dict with status ("running"/"complete"/"failed") and video_url if complete.
    """
    operation = await vertex_ai.get_operation(operation_id)
    if operation.done:
        if operation.error:
            return {"status": "failed", "error": operation.error.message}
        return {"status": "complete", "video_url": operation.result.video_uri}
    return {"status": "running", "progress": operation.metadata.get("progress", 0)}

# Agent instruction for polling
video_producer_agent = LlmAgent(
    instruction="""Generate a video:
    1. Call submit_veo_generation with the script and brand DNA.
    2. Call check_veo_status every 30 seconds until status is "complete" or "failed".
    3. If "failed" after 10 minutes total, escalate.
    4. If "complete", call store_generated_video with the video_url.""",
    tools=[submit_veo_generation, check_veo_status, store_generated_video],
)
```

### Pattern B — Streaming Intermediate Results

```python
from google.adk.tools import ToolContext

async def stream_script_generation(
    brand_dna: dict, platform: str, tool_context: ToolContext
) -> dict:
    """Streams script tokens to the Live Canvas UI in real-time."""
    full_script = ""
    async for token in gemini_stream(build_script_prompt(brand_dna, platform)):
        full_script += token
        tool_context.send_intermediate_result({
            "type": "script_token",
            "token": token,
            "platform": platform,
        })
    return {"status": "complete", "script": full_script}
```

---

## 21. Evaluation & Debugging

### ADK CLI

```bash
adk web                                                   # Dev UI at localhost:8000
adk check-agent brandforge.agent:root_agent              # Validate structure
adk eval brandforge/ --test_file tests/eval_cases.json   # Run evaluations
adk eval brandforge/ --test_file tests/eval_cases.json \
  --eval_metrics response_match tool_trajectory          # Full eval
adk api_server --port 8080 brandforge                    # Production API server
```

### Eval Case Format

```json
[
  {
    "query": "Create a campaign for Grounded sustainable sneakers",
    "expected_tool_calls": ["transcribe_voice_brief", "analyze_brand_assets", "generate_brand_dna"],
    "expected_final_response_contains": ["Brand DNA", "Grounded", "sustainable"]
  }
]
```

### ADK Dev UI Features
- Step-by-step execution inspection (events, state changes per turn)
- Tool call inputs and outputs viewer
- Agent hierarchy visualizer
- Session state inspector in real time
- Switch between agents in multi-agent system

### Structured Cloud Logging

```python
import logging, json

def log_agent_event(agent_name: str, event_type: str, campaign_id: str, data: dict = None):
    logging.info(json.dumps({
        "agent": agent_name,
        "event": event_type,
        "campaign_id": campaign_id,
        "data": data or {},
        "severity": "INFO",
    }))
```

---

## 22. Deployment — Cloud Run & Vertex AI Agent Engine

### Cloud Run

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install uv && uv sync
COPY brandforge/ ./brandforge/
CMD ["adk", "api_server", "--port", "8080", "brandforge"]
```

```bash
gcloud run deploy brandforge \
  --source . --region us-central1 --platform managed \
  --set-env-vars GCP_PROJECT=brandforge-prod
```

### Vertex AI Agent Engine

```python
import vertexai
from vertexai.agent_engines import AdkApp

vertexai.init(project="brandforge-prod", location="us-central1")
app = AdkApp(agent=root_agent)
remote_app = vertexai.agent_engines.create(
    app,
    requirements=["google-adk>=0.3.0", "google-cloud-firestore"],
    display_name="BrandForge Campaign Orchestrator",
)
async for event in remote_app.async_stream_query(user_id=user_id, message=brief_json):
    process_event(event)
```

| Feature | Cloud Run | Vertex AI Agent Engine |
|---|---|---|
| Session management | Manual (DatabaseSessionService) | Automatic (managed) |
| Scaling | Manual configuration | Auto-scaling |
| Memory Bank | Manual integration | Native |
| Best for | Custom infra, full control | Fastest path to production |

---

## 23. Security Guidelines

Always implement defense in depth across all layers.

**Input guardrails:** Use before_model_callback as a fast pre-filter on public-facing agents.
**Tool governance:** Parameterized queries only. Validate all inputs against allowlists.
**Secrets:** All secrets from Secret Manager. Never .env in production, never hardcoded.
**Service accounts:** Dedicated SA per agent role with least-privilege IAM.
**GCS:** Private bucket. All frontend access via signed URLs only.
**Errors:** Never expose stack traces or service names in error responses.
**Callbacks:** Use after_tool_callback to redact tokens/secrets before LLM sees tool output.

---

## 24. Performance Optimization

- Specialize agents: one job per agent. Fewer tools = fewer tokens = lower cost + fewer wrong calls.
- Start with 1-2 tools per agent during development, scale after validation.
- Use ParallelAgent for any 2+ independent tasks. BrandForge 5 production agents always fan out.
- temp: state prefix for large intermediate values. Discarded after turn, never inflates state.
- Connection pooling: singleton Firestore/BigQuery clients per Cloud Run instance.
- Cache TTS narrations by text hash in GCS. Never regenerate the same Sage narration twice.
- tool_filter on McpToolset: only expose tools the agent needs.
- Run adk eval before every release. Tool trajectory regressions are silent bugs without it.
- Use gemini-3.1-pro-preview for production agents. Downgrade to Flash only for latency-critical paths.

---
## 25. BrandForge-Specific Patterns

### Pattern A: Parallel Production Dispatch
Dispatch all 5 production agents simultaneously via Pub/Sub from the Orchestrator.
Each agent publishes its own brandforge.agent.complete event when done.
The Orchestrator waits for all 5 before triggering QA.

### Pattern B: QA Gate with Regeneration
QA Inspector scores asset on 4 dimensions (color, tone, visual_energy, messaging).
Overall score must be >= 0.80 to pass. Failures trigger targeted regeneration.
Max 2 regeneration attempts per asset. Third failure escalates to qa_escalated status.

### Pattern C: A2A Analytics Feedback
Cloud Scheduler triggers Analytics Agent at 24h, 72h, 7d post-publish.
Analytics Agent fetches metrics via MCP, stores in BigQuery, computes PerformanceRanking.
Publishes AnalyticsInsight to brandforge.analytics.insights Pub/Sub topic.
Orchestrator receives insight, updates Brand Memory, pre-populates next campaign template.

### State Key Conventions

Session state:
  campaign_id                     Core campaign identifier
  brand_dna_id                    FK to BrandDNA document
  pending_agents                  List of agents not yet complete
  brand_coherence_score           Campaign-wide QA average
  qa_approved:{asset_id}          Bool: QA approved for this asset
  qa_score:{asset_id}             Float: QA score for this asset
  qa_escalated:{asset_id}         Bool: Escalated past max attempts

User state (persists across campaigns):
  user:brand_id                   Brand identifier
  user:brand_dna_current          Latest Brand DNA ID

Temp state (discarded after turn):
  temp:api_response               Raw API response before processing
  temp:generation_prompt          Imagen/Veo prompt before submission

---
## 26. Common Mistakes and Anti-Patterns

### Bypassing ADK with raw Gemini SDK
WRONG:  import google.generativeai as genai; model.generate_content(...)
CORRECT: Use LlmAgent with model= parameter. Always go through ADK.

### Direct session state mutation
WRONG:  session = await session_service.get_session(...); session.state[key] = value
CORRECT: Mutate only via tool_context.state or callback_context.state inside tools/callbacks.

### Race conditions in ParallelAgent
WRONG:  image_agent and video_agent both use output_key="result" (one overwrites the other)
CORRECT: Each parallel sub-agent must write to a unique state key.

### Missing description on sub-agents
WRONG:  LlmAgent(name="brand_strategist", instruction="...") -- no description
CORRECT: Always include description= for any agent in sub_agents. ADK AutoFlow reads it for routing.

### transfer_to_agent targeting unlisted agent
WRONG:  tool sets transfer_to_agent="qa_inspector" but qa_inspector not in sub_agents
CORRECT: Transfer targets must be listed in the calling agent sub_agents list.

### Schemas defined inside agent files
WRONG:  Pydantic models defined in agents/brand_strategist/agent.py
CORRECT: All schemas in brandforge/shared/models.py. Import into agents.

### Using output_schema and tools together
WRONG:  LlmAgent(tools=[my_tool], output_schema=MyOutput)  -- mutually exclusive
CORRECT: Separate into two agents: one uses tools, one enforces schema via SequentialAgent.

### Hardcoded secrets
WRONG:  GEMINI_API_KEY = "AIzaSy..."
CORRECT: api_key = await get_secret("GEMINI_API_KEY") from Secret Manager

---

## 27. Quick Reference Cheatsheet

### Key Imports
from google.adk.agents import LlmAgent, Agent, SequentialAgent, ParallelAgent, LoopAgent, BaseAgent
from google.adk.tools import FunctionTool, AgentTool, ToolContext
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, SseConnectionParams, StdioConnectionParams
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, DatabaseSessionService
from google.adk.artifacts import InMemoryArtifactService, GcsArtifactService
from google.adk.memory import InMemoryMemoryService, VertexAiMemoryBankService
from google.adk.streaming import LiveRequestQueue
from google.adk.models import LlmResponse
from google.genai import types

### Agent Selection
LLM reasoning + tool use                 -> LlmAgent
Linear pipeline A -> B -> C              -> SequentialAgent
Independent concurrent tasks             -> ParallelAgent
Repeat until condition                   -> LoopAgent
Custom orchestration logic               -> Extend BaseAgent
Specialist as callable tool              -> AgentTool(agent=specialist)
External service tools                   -> McpToolset(connection_params=...)
Real-time voice interaction              -> runner.run_live() + LiveRequestQueue

### ToolContext Action Flags
tool_context.actions.transfer_to_agent = "agent_name"  # Transfer to sub-agent
tool_context.actions.escalate = True                    # Stop + bubble up / exit LoopAgent
tool_context.actions.skip_summarization = True          # Return result directly to user

### CLI Commands
adk web                                                   # Dev UI at localhost:8000
adk api_server --port 8080 brandforge                    # Production API server
adk check-agent brandforge.agent:root_agent              # Validate agent structure
adk eval brandforge/ --test_file tests/eval_cases.json   # Run evaluations

### Modalities and Models
Text only                        -> Any Gemini model
Vision (images, video frames)    -> gemini-3.1-pro-preview+
Audio transcription              -> gemini-3.1-pro-preview+
Live bidirectional voice         -> gemini-3.1-pro-preview (Live API only)
Code execution sandbox           -> gemini-3.1-pro-preview+

### BrandForge Architecture Non-Negotiables
Agent framework       -> LlmAgent via ADK                  (not raw Gemini SDK)
A2A communication     -> Pub/Sub only                       (not direct HTTP)
Social posting        -> MCP protocol only                  (not direct REST)
Secrets               -> Secret Manager only                (not .env or hardcoded)
Schemas               -> shared/models.py only              (not inside agent files)
Business logic        -> tools.py                           (not agent.py)
File storage          -> GCS + Artifacts API                (not local filesystem)
Analytics storage     -> BigQuery                           (not Firestore)
State mutations       -> ToolContext / CallbackContext       (not session.state direct)

---

> **Official docs:** https://google.github.io/adk-docs
> **GitHub:** https://github.com/google/adk-python
> **Samples:** https://github.com/google/adk-samples
> **8 Multi-Agent Patterns:** https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/
> **Streaming guide:** https://google.github.io/adk-docs/streaming/dev-guide/part1/
> **Vertex AI Agent Engine:** https://docs.cloud.google.com/agent-builder/agent-development-kit/overview