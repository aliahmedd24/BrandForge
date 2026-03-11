"""Video Producer Agent — generates videos from scripts using Veo 3.1.

Transforms video scripts into finished video ads with Veo 3.1 for visuals,
Cloud TTS for voiceover, and FFmpeg for final composition.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.video_producer.prompts import VIDEO_PRODUCER_INSTRUCTION
from brandforge.agents.video_producer.tools import (
    compose_final_video,
    generate_voiceover,
    poll_veo_operation,
    submit_veo_generation,
)

logger = logging.getLogger(__name__)

video_producer_agent = LlmAgent(
    name="video_producer",
    model="gemini-2.0-flash",
    description=(
        "Generates video ads using Veo 3.1, adds voiceover via Cloud TTS, "
        "and composes final MP4 files for each platform."
    ),
    instruction=VIDEO_PRODUCER_INSTRUCTION,
    tools=[
        FunctionTool(submit_veo_generation),
        FunctionTool(poll_veo_operation),
        FunctionTool(generate_voiceover),
        FunctionTool(compose_final_video),
    ],
    output_key="generated_videos",
)

logger.info("Video Producer agent initialized (model=gemini-2.0-flash)")
