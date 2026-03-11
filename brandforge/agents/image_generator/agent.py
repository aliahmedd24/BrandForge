"""Image Generator Agent — produces campaign images for all platforms.

Generates production-ready static images using Imagen 4 Ultra with
3 A/B/C variants per platform spec.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.image_generator.prompts import IMAGE_GENERATOR_INSTRUCTION
from brandforge.agents.image_generator.tools import generate_campaign_images

logger = logging.getLogger(__name__)

image_generator_agent = LlmAgent(
    name="image_generator",
    model="gemini-2.0-flash",
    description=(
        "Produces final production-ready static images for all required "
        "platform dimensions using Imagen 4 Ultra with A/B/C variants."
    ),
    instruction=IMAGE_GENERATOR_INSTRUCTION,
    tools=[
        FunctionTool(generate_campaign_images),
    ],
    output_key="generated_images",
)

logger.info("Image Generator agent initialized (model=gemini-2.0-flash)")
