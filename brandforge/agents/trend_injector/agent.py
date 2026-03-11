"""Trend Injector Agent — researches real-time trends before Brand Strategist.

This is the first agent in the BrandForge pipeline. It uses Gemini with
Google Search grounding to inject real-time cultural trends, platform-specific
viral formats, and audience hooks into the campaign context.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.trend_injector.prompts import TREND_INJECTOR_INSTRUCTION
from brandforge.agents.trend_injector.tools import (
    compile_trend_brief,
    research_audience_hooks,
    research_platform_trends,
)

logger = logging.getLogger(__name__)

trend_injector_agent = LlmAgent(
    name="trend_injector",
    model="gemini-2.0-flash",
    description=(
        "Researches real-time cultural trends, platform-specific viral formats, "
        "and audience hooks using Google Search grounding. Runs before "
        "Brand Strategist to ensure campaigns are timely, not generic."
    ),
    instruction=TREND_INJECTOR_INSTRUCTION,
    tools=[
        FunctionTool(research_platform_trends),
        FunctionTool(research_audience_hooks),
        FunctionTool(compile_trend_brief),
    ],
    output_key="trend_brief_result",
)

logger.info("Trend Injector agent initialized (model=gemini-2.0-flash)")
