"""Mood Board Director Agent — generates visual mood boards from Brand DNA.

Creates 6 reference images via Imagen 4 Ultra and assembles them into
a branded PDF mood board with color swatches and typography specs.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.mood_board.prompts import MOOD_BOARD_INSTRUCTION
from brandforge.agents.mood_board.tools import (
    assemble_mood_board_pdf,
    generate_mood_board_images,
)

logger = logging.getLogger(__name__)

mood_board_agent = LlmAgent(
    name="mood_board_director",
    model="gemini-2.0-flash",
    description=(
        "Generates a visual mood board using Imagen 4 Ultra — reference "
        "imagery establishing the visual language for the campaign."
    ),
    instruction=MOOD_BOARD_INSTRUCTION,
    tools=[
        FunctionTool(generate_mood_board_images),
        FunctionTool(assemble_mood_board_pdf),
    ],
    output_key="mood_board",
)

logger.info("Mood Board Director agent initialized (model=gemini-2.0-flash)")
