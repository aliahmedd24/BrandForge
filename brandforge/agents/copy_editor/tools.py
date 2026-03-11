"""FunctionTool implementations for the Copy Editor Agent.

Reviews and refines campaign copy for brand voice compliance,
platform constraints, and forbidden word checking.
"""

import asyncio
import json
import logging
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.copy_editor.prompts import (
    COPY_GENERATION_SYSTEM_PROMPT,
    COPY_GENERATION_USER_PROMPT_TEMPLATE,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import COPY_PACKAGES_COLLECTION, save_document
from brandforge.shared.models import BrandDNA, CopyPackage, PlatformCopy, VideoScript
from brandforge.shared.storage import upload_blob

logger = logging.getLogger(__name__)

AGENT_MODEL = "gemini-2.0-flash"

# Platform character limits
PLATFORM_CHAR_LIMITS = {
    "instagram": 2200,
    "twitter_x": 280,
    "linkedin": 3000,
    "facebook": 2200,
    "tiktok": 2200,
    "youtube": 5000,
}

# Platform hashtag limits
PLATFORM_HASHTAG_LIMITS = {
    "instagram": 30,
    "linkedin": 5,
}

# ── Gemini client singleton ────────────────────────────────────────────

_genai_client: Optional[genai.Client] = None


def _get_genai_client() -> genai.Client:
    """Return a cached google.genai Client configured for Vertex AI."""
    global _genai_client
    if _genai_client is None:
        config = get_vertexai_config()
        _genai_client = genai.Client(
            vertexai=True,
            project=config["project"],
            location=config["location"],
        )
    return _genai_client


# ── Tool: Review and Refine Copy ───────────────────────────────────────


async def review_and_refine_copy(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Generate and validate a complete copy package for all platforms.

    Reads video scripts and Brand DNA from session state. Uses Gemini
    structured output to generate platform-specific copy. Validates
    character limits, hashtag counts, and brand voice scores. Re-prompts
    if constraints are violated.

    Args:
        campaign_id: The campaign to generate copy for.
        tool_context: ADK tool context for state access.

    Returns:
        A dict summary of the copy package.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            logger.error("No brand_dna in session state for campaign %s", real_campaign_id)
            return {"error": "No brand_dna found in session state."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Read scripts for reference
        scripts_data = tool_context.state.get("video_scripts_data", [])
        script_hooks = ""
        if scripts_data:
            hooks = []
            for s in scripts_data:
                script = VideoScript.model_validate(s)
                hooks.append(f"- {script.platform.value} ({script.duration_seconds}s): {script.hook}")
            script_hooks = "\n".join(hooks)
        else:
            script_hooks = "No scripts available yet."

        # Build messaging pillars text
        pillars_text = "\n".join(
            f"- {p.title}: {p.one_liner}" for p in brand_dna.messaging_pillars
        )

        # Determine platforms
        platforms = ", ".join(brand_dna.platform_strategy.keys())

        user_prompt = COPY_GENERATION_USER_PROMPT_TEMPLATE.format(
            brand_name=brand_dna.brand_name,
            brand_essence=brand_dna.brand_essence,
            tone_of_voice=brand_dna.tone_of_voice,
            campaign_goal=brand_dna.source_brief_summary,
            messaging_pillars=pillars_text,
            persona_name=brand_dna.primary_persona.name,
            persona_age_range=brand_dna.primary_persona.age_range,
            do_not_use=", ".join(brand_dna.do_not_use),
            platforms=platforms,
            script_hooks=script_hooks,
            campaign_id=real_campaign_id,
        )

        logger.info("Generating copy package for campaign %s", real_campaign_id)
        client = _get_genai_client()

        # Generate with retry for constraint violations
        max_attempts = 3
        copy_package: Optional[CopyPackage] = None

        for attempt in range(max_attempts):
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=AGENT_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=COPY_GENERATION_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
            )

            raw = json.loads(response.text)
            raw["campaign_id"] = real_campaign_id

            # Validate with Pydantic
            copy_package = CopyPackage.model_validate(raw)

            # Post-validation checks
            violations: list[str] = []

            for pc in copy_package.platform_copies:
                platform = pc.platform.value

                # Check character limits
                char_limit = PLATFORM_CHAR_LIMITS.get(platform, 5000)
                if len(pc.caption) > char_limit:
                    violations.append(
                        f"{platform} caption exceeds {char_limit} chars (got {len(pc.caption)})"
                    )

                # Fix character_count if wrong
                pc.character_count = len(pc.caption)

                # Check hashtag limits
                hashtag_limit = PLATFORM_HASHTAG_LIMITS.get(platform)
                if hashtag_limit and len(pc.hashtags) > hashtag_limit:
                    violations.append(
                        f"{platform} has {len(pc.hashtags)} hashtags (max {hashtag_limit})"
                    )

                # Check brand voice score
                if pc.brand_voice_score < 0.7:
                    violations.append(
                        f"{platform} brand_voice_score {pc.brand_voice_score} < 0.7"
                    )

                # Check forbidden words
                all_text = f"{pc.caption} {pc.headline} {pc.cta_text}".lower()
                for forbidden in brand_dna.do_not_use:
                    word = forbidden.split("(")[0].strip().lower()
                    if word and word in all_text:
                        violations.append(f"{platform} contains forbidden word: '{word}'")

            if not violations:
                break

            logger.warning(
                "Copy package attempt %d has violations: %s. Retrying.",
                attempt + 1, violations,
            )
            # Add violations to prompt for next attempt
            user_prompt += f"\n\nFIX THESE ISSUES:\n" + "\n".join(f"- {v}" for v in violations)

        if copy_package is None:
            raise ValueError("Failed to generate valid copy package after retries.")

        # Upload to GCS
        gcs_path = f"campaigns/{real_campaign_id}/production/copy/copy_package.json"
        json_bytes = copy_package.model_dump_json(indent=2).encode("utf-8")
        await asyncio.to_thread(
            upload_blob,
            source_data=json_bytes,
            destination_path=gcs_path,
            content_type="application/json",
            metadata={"campaign_id": real_campaign_id, "agent_name": "copy_editor"},
        )

        # Save to Firestore
        await save_document(
            COPY_PACKAGES_COLLECTION,
            copy_package.id,
            copy_package.model_dump(mode="json"),
        )

        # Store in session state
        tool_context.state["copy_package_data"] = copy_package.model_dump(mode="json")

        logger.info(
            "Copy package generated for campaign %s (%d platforms)",
            real_campaign_id, len(copy_package.platform_copies),
        )
        return {
            "platforms": [pc.platform.value for pc in copy_package.platform_copies],
            "global_tagline": copy_package.global_tagline,
            "brand_voice_scores": {
                pc.platform.value: pc.brand_voice_score
                for pc in copy_package.platform_copies
            },
        }

    except Exception as exc:
        logger.error(
            "Failed to review and refine copy for campaign %s: %s",
            real_campaign_id, exc,
        )
        return {"error": str(exc)}
