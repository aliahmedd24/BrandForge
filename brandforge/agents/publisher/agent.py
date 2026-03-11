"""Social Publisher agent — posts campaign assets to social platforms via MCP.

All social posting goes through MCP servers. No direct REST calls to social APIs.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from .prompts import PUBLISHER_INSTRUCTION
from .tools import (
    post_image_to_platform,
    post_video_to_platform,
    update_schedule_item_status,
    verify_platform_auth,
)

logger = logging.getLogger(__name__)

publisher_agent = LlmAgent(
    name="publisher",
    model="gemini-2.0-flash",
    description=(
        "MCP-powered agent that executes social media posts at scheduled times. "
        "Posts assets with copy to target platforms and records live post URLs."
    ),
    instruction=PUBLISHER_INSTRUCTION,
    output_key="publish_results",
    tools=[
        FunctionTool(verify_platform_auth),
        FunctionTool(post_image_to_platform),
        FunctionTool(post_video_to_platform),
        FunctionTool(update_schedule_item_status),
    ],
)

logger.info("Social Publisher agent initialized")
