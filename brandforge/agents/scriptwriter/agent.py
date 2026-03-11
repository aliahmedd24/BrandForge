"""Scriptwriter Agent — generates video scripts from Brand DNA.

Produces 15s, 30s, and 60s scripts per platform with scene direction,
voiceover, and emotional beats. Output is consumed by Video Producer
and Copy Editor agents.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.scriptwriter.prompts import SCRIPTWRITER_INSTRUCTION
from brandforge.agents.scriptwriter.tools import generate_video_scripts, store_scripts

logger = logging.getLogger(__name__)

scriptwriter_agent = LlmAgent(
    name="scriptwriter",
    model="gemini-2.0-flash",
    description=(
        "Generates video scripts (15s, 30s, 60s) per platform with "
        "scene-by-scene direction, voiceover, and emotional beats."
    ),
    instruction=SCRIPTWRITER_INSTRUCTION,
    tools=[
        FunctionTool(generate_video_scripts),
        FunctionTool(store_scripts),
    ],
    output_key="video_scripts",
)

logger.info("Scriptwriter agent initialized (model=gemini-2.0-flash)")
