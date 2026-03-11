"""Brand Memory Agent — persistent brand intelligence across campaigns.

Manages a brand's accumulated knowledge: what worked, what failed,
and how the brand has evolved. Pre-populates new campaigns with
intelligence from past performance.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.brand_memory.prompts import BRAND_MEMORY_INSTRUCTION
from brandforge.agents.brand_memory.tools import (
    apply_memory_recommendations,
    fetch_brand_memory,
    update_brand_memory,
)

logger = logging.getLogger(__name__)

brand_memory_agent = LlmAgent(
    name="brand_memory",
    model="gemini-2.0-flash",
    description=(
        "Manages persistent brand intelligence across campaigns. Fetches past "
        "performance data to pre-populate new campaigns and updates memory "
        "after each campaign's analytics run."
    ),
    instruction=BRAND_MEMORY_INSTRUCTION,
    tools=[
        FunctionTool(fetch_brand_memory),
        FunctionTool(apply_memory_recommendations),
        FunctionTool(update_brand_memory),
    ],
    output_key="brand_memory_result",
)

logger.info("Brand Memory agent initialized (model=gemini-2.0-flash)")
