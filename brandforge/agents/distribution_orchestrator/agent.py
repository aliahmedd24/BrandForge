"""Distribution Orchestrator — sequential pipeline: Format Optimizer → Scheduler → Publisher.

Ensures assets are formatted before scheduling, and scheduled before publishing.
"""

import logging

from google.adk.agents import SequentialAgent

from brandforge.agents.format_optimizer.agent import format_optimizer_agent
from brandforge.agents.post_scheduler.agent import post_scheduler_agent
from brandforge.agents.publisher.agent import publisher_agent

logger = logging.getLogger(__name__)

distribution_orchestrator = SequentialAgent(
    name="distribution_orchestrator",
    description=(
        "Distribution pipeline: Format Optimizer ensures correct asset dimensions, "
        "Post Scheduler computes optimal posting times, "
        "Social Publisher posts to platforms via MCP."
    ),
    sub_agents=[format_optimizer_agent, post_scheduler_agent, publisher_agent],
)

logger.info("Distribution Orchestrator initialized (format → schedule → publish)")
