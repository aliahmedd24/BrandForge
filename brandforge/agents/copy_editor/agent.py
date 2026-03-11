"""Copy Editor Agent — reviews and refines campaign copy.

Ensures brand voice compliance, platform character limits,
hashtag counts, and forbidden word checking across all platforms.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.copy_editor.prompts import COPY_EDITOR_INSTRUCTION
from brandforge.agents.copy_editor.tools import review_and_refine_copy

logger = logging.getLogger(__name__)

copy_editor_agent = LlmAgent(
    name="copy_editor",
    model="gemini-2.0-flash",
    description=(
        "Reviews and refines all campaign copy for brand voice compliance, "
        "grammar, and platform-specific best practices."
    ),
    instruction=COPY_EDITOR_INSTRUCTION,
    tools=[
        FunctionTool(review_and_refine_copy),
    ],
    output_key="approved_copy",
)

logger.info("Copy Editor agent initialized (model=gemini-2.0-flash)")
