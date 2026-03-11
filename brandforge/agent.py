"""Root ADK agent entry point for BrandForge.

This module defines the root_agent variable that ADK discovers
via brandforge/__init__.py → from . import agent.
"""

import logging
import sys

from google.adk.agents import ParallelAgent, SequentialAgent

from brandforge.agents.brand_memory.agent import brand_memory_agent
from brandforge.agents.brand_strategist.agent import brand_strategist_agent
from brandforge.agents.campaign_assembler.agent import campaign_assembler_agent
from brandforge.agents.competitor_intel.agent import competitor_intel_agent
from brandforge.agents.distribution_orchestrator.agent import distribution_orchestrator
from brandforge.agents.production_orchestrator.agent import production_orchestrator
from brandforge.agents.qa_inspector.agent import qa_inspector_agent
from brandforge.agents.sage.agent import sage_agent
from brandforge.agents.trend_injector.agent import trend_injector_agent

# ── Structured JSON logging ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    stream=sys.stderr,
)

logger = logging.getLogger("brandforge")

# ── Pre-Strategy Intelligence: Trend Injector + Competitor Intel + Brand Memory
# These three agents run in parallel BEFORE Brand Strategist to inject
# real-time trends, competitor analysis, and brand memory into the context.

pre_strategy_intel = ParallelAgent(
    name="pre_strategy_intel",
    description=(
        "Pre-strategy intelligence gathering. Runs Trend Injector, "
        "Competitor Intelligence, and Brand Memory fetch in parallel "
        "before Brand Strategist."
    ),
    sub_agents=[trend_injector_agent, competitor_intel_agent, brand_memory_agent],
)

# ── QA Orchestrator: QA Inspector → Campaign Assembler ──────────────────

qa_orchestrator = SequentialAgent(
    name="qa_orchestrator",
    description=(
        "QA gate and campaign assembly pipeline. QA Inspector reviews "
        "all assets, then Campaign Assembler packages approved assets."
    ),
    sub_agents=[qa_inspector_agent, campaign_assembler_agent],
)

# ── Root Agent ───────────────────────────────────────────────────────────
# SequentialAgent guarantees all phases run in order:
#   1. Pre-Strategy Intel → Trends, competitors, brand memory (parallel)
#   2. Brand Strategist   → Brand DNA (informed by trends/competitors/memory)
#   3. Production         → Scripts, images, videos, copy
#   4. QA + Assembly      → Review & package
#   5. Distribution       → Format, schedule, publish
#   6. Sage               → Campaign debrief narration

root_agent = SequentialAgent(
    name="brandforge_root",
    description=(
        "BrandForge root pipeline. Runs pre-strategy intelligence, brand strategy, "
        "creative production, QA/assembly, distribution, and Sage narration in sequence."
    ),
    sub_agents=[
        pre_strategy_intel,
        brand_strategist_agent,
        production_orchestrator,
        qa_orchestrator,
        distribution_orchestrator,
        sage_agent,
    ],
)

logger.info(
    "BrandForge root agent initialized (sequential pipeline, "
    "sub_agents=[pre_strategy_intel, brand_strategist, production_orchestrator, "
    "qa_orchestrator, distribution_orchestrator, sage])"
)
