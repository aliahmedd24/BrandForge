"""Competitor Intelligence Agent — analyzes competitors via screenshots + Vision.

Uses Playwright for screenshot capture and Gemini Vision for structured
brand analysis. Generates a competitive positioning map and differentiation
strategy injected into Brand Strategist context.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.competitor_intel.prompts import COMPETITOR_INTEL_INSTRUCTION
from brandforge.agents.competitor_intel.tools import (
    analyze_competitor_brand,
    capture_competitor_screenshot,
    generate_competitor_map,
)

logger = logging.getLogger(__name__)

competitor_intel_agent = LlmAgent(
    name="competitor_intel",
    model="gemini-2.0-flash",
    description=(
        "Analyzes competitor brands using Playwright screenshots and Gemini "
        "Vision. Extracts visual language, tone, and positioning to generate "
        "a competitive differentiation strategy and positioning map."
    ),
    instruction=COMPETITOR_INTEL_INSTRUCTION,
    tools=[
        FunctionTool(capture_competitor_screenshot),
        FunctionTool(analyze_competitor_brand),
        FunctionTool(generate_competitor_map),
    ],
    output_key="competitor_map_result",
)

logger.info("Competitor Intelligence agent initialized (model=gemini-2.0-flash)")
