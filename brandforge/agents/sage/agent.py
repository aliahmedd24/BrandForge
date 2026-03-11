"""Sage Voice Orchestrator — BrandForge's AI Creative Director persona.

Narrates the campaign generation process using Cloud TTS, processes
voice feedback via Gemini, and delivers spoken briefings. Gives
BrandForge a distinct voice and personality.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.sage.prompts import SAGE_INSTRUCTION
from brandforge.agents.sage.tools import (
    narrate_agent_milestone,
    process_voice_feedback,
)

logger = logging.getLogger(__name__)

sage_agent = LlmAgent(
    name="sage",
    model="gemini-2.0-flash",
    description=(
        "Sage — BrandForge's AI Creative Director. Narrates campaign "
        "milestones via Cloud TTS, processes voice feedback, and delivers "
        "spoken briefings. Provides the voice personality of BrandForge."
    ),
    instruction=SAGE_INSTRUCTION,
    tools=[
        FunctionTool(narrate_agent_milestone),
        FunctionTool(process_voice_feedback),
    ],
    output_key="sage_result",
)

logger.info("Sage Voice Orchestrator initialized (model=gemini-2.0-flash)")
