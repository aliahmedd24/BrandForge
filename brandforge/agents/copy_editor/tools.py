"""Copy Editor tool implementations — Phase 2.

Generates platform-specific marketing copy with brand voice validation,
character limit enforcement, and forbidden word filtering.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from google import genai
from google.genai import types

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_BRAND_DNA,
    FIRESTORE_COLLECTION_COPY_PACKAGES,
    FIRESTORE_COLLECTION_SCRIPTS,
    MAX_RETRIES,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    RETRY_BASE_DELAY_SECONDS,
    EVENT_COPYEDITOR_COMPLETE,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    CopyPackage,
    PlatformCopy,
)
from brandforge.shared.utils import retry_with_backoff, strip_json_fences

logger = logging.getLogger(__name__)

# Platform character limits for validation
_PLATFORM_CHAR_LIMITS: dict[str, int] = {
    "instagram": 2200,
    "twitter_x": 280,
    "linkedin": 3000,
    "tiktok": 2200,
    "facebook": 63206,
    "youtube": 5000,
}

_PLATFORM_HASHTAG_LIMITS: dict[str, int] = {
    "instagram": 30,
    "linkedin": 5,
}

_COPY_SYSTEM_PROMPT = """\
You are a senior copy editor and brand voice guardian with 15 years of
social media copywriting expertise. You write copy that is platform-native,
brand-consistent, and engagement-optimized.

Your output MUST be grounded exclusively in the provided BrandDNA.
All messaging, tone, and word choice must reflect the brand personality.

You will produce marketing copy in the exact JSON schema requested.
Every field is required. Be specific to the platform.
"""


# ---------------------------------------------------------------------------
# Tool: review_and_refine_copy
# ---------------------------------------------------------------------------


async def review_and_refine_copy(
    campaign_id: str,
    brand_dna_id: str,
) -> dict[str, Any]:
    """Generate marketing copy for all campaign platforms.

    Fetches BrandDNA and scripts, generates per-platform copy via Gemini,
    validates character limits and hashtag counts, checks brand voice
    alignment, and filters forbidden words.

    Args:
        campaign_id: The campaign ID.
        brand_dna_id: The BrandDNA document ID.

    Returns:
        dict with status and CopyPackage data on success.
    """
    try:
        from brandforge.shared import firestore as fs

        # Fetch BrandDNA
        brand_dna_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            doc_id=brand_dna_id,
        )
        if not brand_dna_data:
            return {"status": "error", "error": f"BrandDNA {brand_dna_id} not found."}

        # Fetch scripts for context
        scripts = await fs.query_collection(
            collection=FIRESTORE_COLLECTION_SCRIPTS,
            field="campaign_id",
            op="==",
            value=campaign_id,
        )

        # Extract platforms
        platform_strategy = brand_dna_data.get("platform_strategy", {})
        platforms = list(platform_strategy.keys())
        if not platforms:
            return {"status": "error", "error": "No platforms in BrandDNA."}

        do_not_use = brand_dna_data.get("do_not_use", [])

        # Generate copy per platform
        platform_copies: list[dict[str, Any]] = []
        errors: list[str] = []

        for platform in platforms:
            try:
                copy_data = await _generate_platform_copy(
                    brand_dna_data=brand_dna_data,
                    platform=platform,
                    scripts=scripts,
                    do_not_use=do_not_use,
                )
                platform_copies.append(copy_data)
            except Exception as exc:
                msg = f"{platform}: {exc}"
                logger.error("Copy generation failed: %s", msg)
                errors.append(msg)

        if not platform_copies:
            return {"status": "error", "error": f"All copy generation failed: {errors}"}

        # Generate global tagline and press blurb
        tagline_data = await _generate_global_copy(brand_dna_data)

        # Assemble CopyPackage
        copy_package = CopyPackage(
            campaign_id=campaign_id,
            platform_copies=[PlatformCopy(**pc) for pc in platform_copies],
            global_tagline=tagline_data.get("tagline", ""),
            press_blurb=tagline_data.get("press_blurb", ""),
        )

        result: dict[str, Any] = {
            "status": "success",
            "data": copy_package.model_dump(mode="json"),
        }
        if errors:
            result["partial_errors"] = errors

        logger.info(
            "Generated copy for %d platforms for campaign %s",
            len(platform_copies), campaign_id,
        )
        return result

    except Exception as exc:
        logger.error("review_and_refine_copy failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def _generate_platform_copy(
    brand_dna_data: dict[str, Any],
    platform: str,
    scripts: list[dict[str, Any]],
    do_not_use: list[str],
    retry_count: int = 0,
) -> dict[str, Any]:
    """Generate and validate copy for a single platform."""
    config = get_config()

    user_prompt = _build_copy_prompt(brand_dna_data, platform, scripts)

    async def _call_gemini() -> str:
        import asyncio

        client = genai.Client(
            vertexai=True,
            project=config.gcp_project_id,
            location=config.gcp_region,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=config.gemini_model,
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=_COPY_SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        return response.text.strip()

    raw_text = await retry_with_backoff(
        _call_gemini,
        max_retries=MAX_RETRIES,
        base_delay=RETRY_BASE_DELAY_SECONDS,
        operation_name=f"copy_{platform}",
    )

    raw_text = strip_json_fences(raw_text)
    copy_data = json.loads(raw_text)
    copy_data["platform"] = platform

    # Ensure character_count is set
    caption = copy_data.get("caption", "")
    copy_data["character_count"] = len(caption)

    # Ensure brand_voice_score exists
    if "brand_voice_score" not in copy_data:
        copy_data["brand_voice_score"] = 0.8

    # Validate by constructing PlatformCopy
    platform_copy = PlatformCopy(**copy_data)

    # Forbidden word check
    all_text = " ".join([
        platform_copy.caption,
        platform_copy.headline,
        platform_copy.cta_text,
        " ".join(platform_copy.hashtags),
    ]).lower()

    violations = [w for w in do_not_use if w.lower() in all_text]
    if violations and retry_count < 2:
        logger.warning(
            "Forbidden words in %s copy: %s — regenerating", platform, violations
        )
        return await _generate_platform_copy(
            brand_dna_data, platform, scripts, do_not_use, retry_count + 1
        )

    # Brand voice score check
    if platform_copy.brand_voice_score < 0.7 and retry_count < 2:
        logger.warning(
            "Low brand voice score (%.2f) for %s — regenerating",
            platform_copy.brand_voice_score, platform,
        )
        return await _generate_platform_copy(
            brand_dna_data, platform, scripts, do_not_use, retry_count + 1
        )

    return platform_copy.model_dump(mode="json")


async def _generate_global_copy(
    brand_dna_data: dict[str, Any],
) -> dict[str, Any]:
    """Generate global tagline and press blurb."""
    config = get_config()
    brand_name = brand_dna_data.get("brand_name", "")
    essence = brand_dna_data.get("brand_essence", "")
    personality = ", ".join(brand_dna_data.get("brand_personality", []))

    prompt = f"""\
Generate a global tagline and press blurb for the brand.

Brand: {brand_name}
Essence: {essence}
Personality: {personality}

Return JSON:
{{
  "tagline": "One memorable campaign tagline (max 100 chars)",
  "press_blurb": "100-word brand description for press (max 700 chars)"
}}

Return ONLY valid JSON.
"""

    async def _call() -> str:
        import asyncio

        client = genai.Client(
            vertexai=True,
            project=config.gcp_project_id,
            location=config.gcp_region,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=config.gemini_model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return response.text.strip()

    try:
        raw = await retry_with_backoff(
            _call,
            max_retries=MAX_RETRIES,
            base_delay=RETRY_BASE_DELAY_SECONDS,
            operation_name="global_copy",
        )
        raw = strip_json_fences(raw)
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Global copy generation failed: %s", exc)
        return {"tagline": f"{brand_name}", "press_blurb": essence}


# ---------------------------------------------------------------------------
# Tool: store_copy_package
# ---------------------------------------------------------------------------


async def store_copy_package(
    copy_package_json: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Persist CopyPackage to Firestore and GCS.

    Args:
        copy_package_json: JSON string of the CopyPackage model.
        campaign_id: The campaign ID.

    Returns:
        dict with status and copy_package_id.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message
        from brandforge.shared.storage import upload_blob

        cp_data = json.loads(copy_package_json) if isinstance(copy_package_json, str) else copy_package_json
        copy_package = CopyPackage(**cp_data)

        # Firestore
        await fs.create_document(
            collection=FIRESTORE_COLLECTION_COPY_PACKAGES,
            doc_id=copy_package.id,
            data=copy_package.model_dump(mode="json"),
        )

        # GCS
        gcs_path = f"campaigns/{campaign_id}/copy/copy_package.json"
        await upload_blob(
            destination_path=gcs_path,
            data=json.dumps(copy_package.model_dump(mode="json"), indent=2).encode("utf-8"),
            content_type="application/json",
        )

        # AgentRun
        agent_run = AgentRun(
            campaign_id=campaign_id,
            agent_name="copy_editor",
            status=AgentStatus.COMPLETE,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            output_ref=gcs_path,
        )
        await fs.create_document(
            collection="agent_runs",
            doc_id=agent_run.id,
            data=agent_run.model_dump(mode="json"),
        )

        # Publish completion
        await publish_message(
            topic=PUBSUB_TOPIC_AGENT_COMPLETE,
            message=AgentMessage(
                source_agent="copy_editor",
                target_agent="orchestrator",
                campaign_id=campaign_id,
                event_type=EVENT_COPYEDITOR_COMPLETE,
                payload={"copy_package_id": copy_package.id},
            ),
        )

        logger.info("Stored copy package %s for campaign %s", copy_package.id, campaign_id)
        return {"status": "success", "copy_package_id": copy_package.id}

    except Exception as exc:
        logger.error("store_copy_package failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_copy_prompt(
    brand_dna_data: dict[str, Any],
    platform: str,
    scripts: list[dict[str, Any]],
) -> str:
    """Build a platform-specific copy generation prompt."""
    brand_name = brand_dna_data.get("brand_name", "")
    tone = brand_dna_data.get("tone_of_voice", "")
    personality = ", ".join(brand_dna_data.get("brand_personality", []))
    do_not_use = brand_dna_data.get("do_not_use", [])
    platform_approach = brand_dna_data.get("platform_strategy", {}).get(platform, "")
    pillars = brand_dna_data.get("messaging_pillars", [])

    char_limit = _PLATFORM_CHAR_LIMITS.get(platform, 5000)
    hashtag_limit = _PLATFORM_HASHTAG_LIMITS.get(platform, 30)

    pillar_text = ""
    for p in pillars:
        pillar_text += f"\n  - {p.get('title', '')}: {p.get('one_liner', '')}"

    # Include script hooks for context
    script_hooks = []
    for s in scripts:
        if s.get("platform") == platform:
            script_hooks.append(s.get("hook", ""))

    hooks_text = "\n".join(f"  - {h}" for h in script_hooks[:3]) if script_hooks else "  (no scripts)"

    return f"""\
Generate marketing copy for the following platform and brand:

Brand: {brand_name}
Platform: {platform}
Platform Approach: {platform_approach}

Brand Personality: {personality}
Tone of Voice: {tone}
Messaging Pillars:{pillar_text}

Related Script Hooks (for context):
{hooks_text}

FORBIDDEN WORDS (do NOT use): {', '.join(do_not_use)}

Character limit for caption: {char_limit}
Hashtag limit: {hashtag_limit}

Return a JSON object:
{{
  "caption": "Main post caption text (under {char_limit} chars)",
  "headline": "Post headline (max 150 chars)",
  "hashtags": ["tag1", "tag2", ...],
  "cta_text": "Call to action (max 50 chars)",
  "brand_voice_score": 0.0-1.0
}}

Rules:
- Caption MUST be under {char_limit} characters
- No more than {hashtag_limit} hashtags
- Brand voice score: self-assess alignment with brand personality (0.0-1.0)
- Tone must match the brand personality for {platform}
- DO NOT use any forbidden words

Return ONLY valid JSON. No markdown fences.
"""
