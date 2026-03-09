"""Brand Strategist Agent — analyzes brand briefs and produces Brand DNA.

This is the first agent in the BrandForge pipeline. It accepts a brand
brief (text, images, audio) and generates a structured BrandDNA document
that all downstream creative agents reference.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.brand_strategist.prompts import BRAND_STRATEGIST_INSTRUCTION
from brandforge.agents.brand_strategist.tools import (
    analyze_brand_assets,
    generate_brand_dna,
    store_brand_dna,
    transcribe_voice_brief,
)

logger = logging.getLogger(__name__)

brand_strategist_agent = LlmAgent(
    name="brand_strategist",
    model="gemini-2.0-flash",
    description=(
        "Analyzes brand briefs (text, images, audio) and produces "
        "a structured Brand DNA document used by all downstream creative agents."
    ),
    instruction=BRAND_STRATEGIST_INSTRUCTION,
    tools=[
        FunctionTool(transcribe_voice_brief),
        FunctionTool(analyze_brand_assets),
        FunctionTool(generate_brand_dna),
        FunctionTool(store_brand_dna),
    ],
    output_key="brand_dna_result",
)

logger.info("Brand Strategist agent initialized (model=gemini-2.0-flash)")
