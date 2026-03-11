"""Root ADK agent entry point for BrandForge.

This module defines the root_agent variable that ADK discovers
via brandforge/__init__.py → from . import agent.
"""

import logging
import sys

from google.adk.agents import SequentialAgent

from brandforge.agents.brand_strategist.agent import brand_strategist_agent
from brandforge.agents.campaign_assembler.agent import campaign_assembler_agent
from brandforge.agents.production_orchestrator.agent import production_orchestrator
from brandforge.agents.qa_inspector.agent import qa_inspector_agent

# ── Structured JSON logging ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    stream=sys.stderr,
)

logger = logging.getLogger("brandforge")

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
# SequentialAgent guarantees all three phases run in order:
#   1. Brand Strategist  → Brand DNA
#   2. Production         → Scripts, images, videos, copy
#   3. QA + Assembly      → Review & package

root_agent = SequentialAgent(
    name="brandforge_root",
    description="BrandForge root pipeline. Runs brand strategy, creative production, QA, and assembly in sequence.",
    sub_agents=[brand_strategist_agent, production_orchestrator, qa_orchestrator],
)

logger.info(
    "BrandForge root agent initialized (sequential pipeline, "
    "sub_agents=[brand_strategist, production_orchestrator, qa_orchestrator])"
)
