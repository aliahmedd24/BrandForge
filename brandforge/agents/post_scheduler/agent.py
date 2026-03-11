"""Post Scheduler agent — computes optimal posting schedule for each platform.

Uses Gemini with Google Search grounding for real posting time data.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from .prompts import POST_SCHEDULER_INSTRUCTION
from .tools import (
    export_calendar_ics,
    generate_posting_calendar,
    research_optimal_posting_times,
    schedule_cloud_jobs,
)

logger = logging.getLogger(__name__)

post_scheduler_agent = LlmAgent(
    name="post_scheduler",
    model="gemini-2.0-flash",
    description=(
        "Computes the optimal posting schedule for each platform and asset "
        "using Gemini with Google Search grounding. Outputs a 2-week posting calendar."
    ),
    instruction=POST_SCHEDULER_INSTRUCTION,
    output_key="posting_schedule",
    tools=[
        FunctionTool(research_optimal_posting_times),
        FunctionTool(generate_posting_calendar),
        FunctionTool(export_calendar_ics),
        FunctionTool(schedule_cloud_jobs),
    ],
)

logger.info("Post Scheduler agent initialized")
