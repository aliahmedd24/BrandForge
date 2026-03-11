"""Format Optimizer agent — resizes images and transcodes videos for each platform.

Reads platform specs from config, not hardcoded in agent logic.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from .prompts import FORMAT_OPTIMIZER_INSTRUCTION
from .tools import optimize_image_for_platform, optimize_video_for_platform

logger = logging.getLogger(__name__)

format_optimizer_agent = LlmAgent(
    name="format_optimizer",
    model="gemini-2.0-flash",
    description=(
        "Ensures every asset is correctly sized and formatted for each "
        "target platform before posting. Uses Pillow for images and FFmpeg for videos."
    ),
    instruction=FORMAT_OPTIMIZER_INSTRUCTION,
    output_key="optimized_assets",
    tools=[
        FunctionTool(optimize_image_for_platform),
        FunctionTool(optimize_video_for_platform),
    ],
)

logger.info("Format Optimizer agent initialized")
