"""Analytics Agent — reads engagement data, computes insights, delivers via A2A.

Deployed as a separate Cloud Run service, communicates with Orchestrator
via ADK A2A (RemoteA2aAgent / to_a2a()).
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from .prompts import ANALYTICS_INSTRUCTION
from .tools import (
    compute_performance_rankings,
    deliver_a2a_insights,
    fetch_platform_metrics,
    generate_insight_report,
    store_metrics_to_bigquery,
)

logger = logging.getLogger(__name__)

analytics_agent = LlmAgent(
    name="analytics_agent",
    model="gemini-2.0-flash",
    description=(
        "Reads social media engagement data for a published campaign, "
        "identifies performance patterns, and generates creative recommendations "
        "for the next campaign iteration via A2A feedback."
    ),
    instruction=ANALYTICS_INSTRUCTION,
    output_key="analytics_insight",
    tools=[
        FunctionTool(fetch_platform_metrics),
        FunctionTool(store_metrics_to_bigquery),
        FunctionTool(compute_performance_rankings),
        FunctionTool(generate_insight_report),
        FunctionTool(deliver_a2a_insights),
    ],
)

logger.info("Analytics Agent initialized")
