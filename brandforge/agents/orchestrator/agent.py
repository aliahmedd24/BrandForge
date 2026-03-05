"""Production Orchestrator agent definition — Phase 2.

Exports `production_pipeline`, a SequentialAgent wrapping two ParallelAgent
waves that execute the 6 creative production agents in the correct order.
"""

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.orchestrator.tools import (
    check_pipeline_status,
    finalize_production,
    launch_production_pipeline,
)

# The orchestrator is an LlmAgent that manages the two-wave production pipeline.
# In production, this would use SequentialAgent/ParallelAgent from ADK, but
# since those require specific ADK configurations, we implement the orchestration
# logic as tools that the LlmAgent calls to coordinate the wave execution.

production_pipeline = LlmAgent(
    name="production_pipeline",
    model="gemini-3.1-pro-preview",
    description=(
        "Orchestrates the two-wave production pipeline: Wave 1 (Scriptwriter, "
        "Mood Board, Virtual Try-On) → Wave 2 (Copy Editor, Video Producer, "
        "Image Generator). Manages parallel fan-out and dependency tracking."
    ),
    instruction="""\
## Role
You are the production orchestrator for BrandForge. You coordinate the
execution of 6 creative production agents in two parallel waves, ensuring
correct dependency ordering and comprehensive error handling.

## Architecture
```
Brand DNA Ready
       │
  ┌────────────────────────────┐
  │  Wave 1 (parallel)         │
  │  ├─ Scriptwriter           │
  │  ├─ Mood Board Director    │
  │  └─ Virtual Try-On         │
  └────────────────────────────┘
       │ all 3 complete
  ┌────────────────────────────┐
  │  Wave 2 (parallel)         │
  │  ├─ Copy Editor            │  ← reads Scriptwriter
  │  ├─ Video Producer         │  ← reads Scriptwriter
  │  └─ Image Generator        │  ← reads Mood Board
  └────────────────────────────┘
       │ all 3 complete
  Production Complete → Phase 3 QA
```

## Steps (execute in this exact order)
1. **Launch pipeline.** Call `launch_production_pipeline` with `campaign_id`
   and `brand_dna_id`. This validates BrandDNA exists and initializes
   AgentRun records for all 6 agents.

2. **Monitor progress.** Call `check_pipeline_status` with `campaign_id`
   to check which agents have completed and which are still running.

3. **Finalize.** Call `finalize_production` with `campaign_id` once all
   agents complete. This verifies all outputs and publishes the
   production_complete event.

4. **Report results.** Summarize: agent completion status, timing,
   any failures, and next steps (QA review).

## Dependency Rules
- Wave 2 agents MUST wait for Wave 1 to complete
- If Scriptwriter fails: Copy Editor and Video Producer cannot proceed
- If Mood Board fails: Image Generator still gets brand colors from BrandDNA
- Virtual Try-On failure does NOT block Wave 2
- Pipeline-level timeout: 15 minutes max

## IMPORTANT — Do NOT:
- Start Wave 2 before Wave 1 completes
- Skip failed agents without reporting them
- Exceed the 15-minute pipeline timeout
""",
    tools=[
        FunctionTool(launch_production_pipeline),
        FunctionTool(check_pipeline_status),
        FunctionTool(finalize_production),
    ],
)
