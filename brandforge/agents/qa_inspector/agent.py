"""Brand QA Inspector Agent — multimodal brand quality gatekeeper.

Reviews all generated campaign assets (images, videos, copy) against
the Brand DNA document. Scores each asset, approves or rejects with
actionable violation notes, and triggers regeneration for failures.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.qa_inspector.prompts import QA_INSPECTOR_INSTRUCTION
from brandforge.agents.qa_inspector.tools import (
    compute_brand_coherence_score,
    generate_correction_prompt,
    review_copy_asset,
    review_image_asset,
    review_video_asset,
    store_qa_result,
    trigger_regeneration,
)

logger = logging.getLogger(__name__)

qa_inspector_agent = LlmAgent(
    name="brand_qa_inspector",
    model="gemini-2.0-flash",
    description=(
        "Multimodal brand quality inspector. Reviews all generated "
        "assets against Brand DNA. Scores, approves, or rejects each "
        "asset with specific, actionable violation notes."
    ),
    instruction=QA_INSPECTOR_INSTRUCTION,
    output_key="qa_result",
    tools=[
        FunctionTool(review_image_asset),
        FunctionTool(review_video_asset),
        FunctionTool(review_copy_asset),
        FunctionTool(store_qa_result),
        FunctionTool(generate_correction_prompt),
        FunctionTool(compute_brand_coherence_score),
        FunctionTool(trigger_regeneration),
    ],
)

logger.info("QA Inspector agent initialized (model=gemini-2.0-flash)")
