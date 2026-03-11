"""Campaign Assembler Agent — packages all QA-approved assets.

Runs after QA Inspector completes. Generates a brand kit PDF,
posting schedule, and ZIP archive of all approved campaign assets.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.campaign_assembler.prompts import (
    CAMPAIGN_ASSEMBLER_INSTRUCTION,
)
from brandforge.agents.campaign_assembler.tools import (
    collect_approved_assets,
    create_asset_bundle_zip,
    generate_brand_kit_pdf,
    generate_posting_schedule,
    store_asset_bundle,
)

logger = logging.getLogger(__name__)

campaign_assembler_agent = LlmAgent(
    name="campaign_assembler",
    model="gemini-2.0-flash",
    description=(
        "Packages all QA-approved campaign assets into a structured bundle. "
        "Generates brand kit PDF, posting schedule, and asset ZIP."
    ),
    instruction=CAMPAIGN_ASSEMBLER_INSTRUCTION,
    output_key="asset_bundle",
    tools=[
        FunctionTool(collect_approved_assets),
        FunctionTool(generate_brand_kit_pdf),
        FunctionTool(generate_posting_schedule),
        FunctionTool(create_asset_bundle_zip),
        FunctionTool(store_asset_bundle),
    ],
)

logger.info("Campaign Assembler agent initialized (model=gemini-2.0-flash)")
