"""Scriptwriter tool implementations — Phase 2.

Generates platform-optimised video scripts (15s, 30s, 60s) for all
campaign platforms, validates against BrandDNA constraints, and stores
results in Firestore + GCS.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from google import genai
from google.genai import types

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_BRAND_DNA,
    FIRESTORE_COLLECTION_SCRIPTS,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    EVENT_SCRIPTWRITER_COMPLETE,
    MAX_RETRIES,
    RETRY_BASE_DELAY_SECONDS,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    VideoScript,
)
from brandforge.shared.utils import retry_with_backoff, strip_json_fences

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ASPECT_RATIO_MAP: dict[str, str] = {
    "tiktok": "9:16",
    "instagram": "9:16",
    "youtube": "16:9",
    "linkedin": "16:9",
    "twitter_x": "16:9",
    "facebook": "1:1",
}

_DURATIONS = [15, 30, 60]

_SCRIPT_SYSTEM_PROMPT = """\
You are a senior creative director with 15 years of experience in short-form
video advertising. You write scripts that capture attention within 3 seconds
and drive measurable engagement.

Your output MUST be grounded exclusively in the provided BrandDNA.
All messaging, tone, visual descriptions, and creative direction must
reference the brand's personality, color palette, visual direction, and
messaging pillars.

You will produce video scripts in the exact JSON schema requested.
Every field is required. Be specific and platform-aware.
"""


# ---------------------------------------------------------------------------
# Tool: generate_video_scripts
# ---------------------------------------------------------------------------


async def generate_video_scripts(
    campaign_id: str,
    brand_dna_id: str,
) -> dict[str, Any]:
    """Generate video scripts for all platforms and durations.

    Fetches BrandDNA from Firestore, then generates a VideoScript for each
    platform × duration (15s, 30s, 60s) combination. Each script is validated
    against BrandDNA forbidden words. Failed platforms are skipped with
    partial success support.

    Args:
        campaign_id: The campaign ID.
        brand_dna_id: The BrandDNA document ID in Firestore.

    Returns:
        dict with status and list of VideoScript dicts on success.
    """
    try:
        from brandforge.shared import firestore as fs

        # 1. Fetch BrandDNA
        brand_dna_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            doc_id=brand_dna_id,
        )
        if not brand_dna_data:
            return {"status": "error", "error": f"BrandDNA {brand_dna_id} not found."}

        # 2. Extract platform list + forbidden words
        platform_strategy = brand_dna_data.get("platform_strategy", {})
        platforms = list(platform_strategy.keys())
        if not platforms:
            return {"status": "error", "error": "No platforms defined in BrandDNA."}

        do_not_use = brand_dna_data.get("do_not_use", [])
        brand_dna_version = brand_dna_data.get("version", 1)

        # 3. Generate scripts per platform × duration
        all_scripts: list[dict[str, Any]] = []
        errors: list[str] = []

        for platform in platforms:
            aspect_ratio = _ASPECT_RATIO_MAP.get(platform, "16:9")
            for duration in _DURATIONS:
                try:
                    script_data = await _generate_single_script(
                        campaign_id=campaign_id,
                        brand_dna_data=brand_dna_data,
                        platform=platform,
                        duration=duration,
                        aspect_ratio=aspect_ratio,
                        brand_dna_version=brand_dna_version,
                        do_not_use=do_not_use,
                    )
                    all_scripts.append(script_data)
                except Exception as exc:
                    msg = f"{platform}/{duration}s: {exc}"
                    logger.error("Script generation failed: %s", msg)
                    errors.append(msg)

        if not all_scripts:
            return {
                "status": "error",
                "error": f"All script generations failed: {errors}",
            }

        result: dict[str, Any] = {
            "status": "success",
            "data": all_scripts,
            "scripts_count": len(all_scripts),
        }
        if errors:
            result["partial_errors"] = errors

        logger.info(
            "Generated %d scripts for campaign %s (%d errors)",
            len(all_scripts), campaign_id, len(errors),
        )
        return result

    except Exception as exc:
        logger.error("generate_video_scripts failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def _generate_single_script(
    campaign_id: str,
    brand_dna_data: dict[str, Any],
    platform: str,
    duration: int,
    aspect_ratio: str,
    brand_dna_version: int,
    do_not_use: list[str],
) -> dict[str, Any]:
    """Generate a single VideoScript via Gemini with retry + forbidden-word check."""
    config = get_config()

    user_prompt = _build_script_prompt(
        brand_dna_data=brand_dna_data,
        platform=platform,
        duration=duration,
        aspect_ratio=aspect_ratio,
    )

    async def _call_gemini() -> str:
        client = genai.Client(
            vertexai=True,
            project=config.gcp_project_id,
            location=config.gcp_region,
        )
        import asyncio

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=config.gemini_model,
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=_SCRIPT_SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        return response.text.strip()

    raw_text = await retry_with_backoff(
        _call_gemini,
        max_retries=MAX_RETRIES,
        base_delay=RETRY_BASE_DELAY_SECONDS,
        operation_name=f"script_{platform}_{duration}s",
    )

    raw_text = strip_json_fences(raw_text)
    script_data = json.loads(raw_text)

    # Inject required fields
    script_data["campaign_id"] = campaign_id
    script_data["platform"] = platform
    script_data["duration_seconds"] = duration
    script_data["aspect_ratio"] = aspect_ratio
    script_data["brand_dna_version"] = brand_dna_version
    if "id" not in script_data:
        script_data["id"] = str(uuid.uuid4())

    # Validate with Pydantic
    script = VideoScript(**script_data)

    # Forbidden word check
    _check_forbidden_words(script, do_not_use)

    return script.model_dump(mode="json")


def _check_forbidden_words(script: VideoScript, do_not_use: list[str]) -> None:
    """Check all text fields of a script against forbidden words.

    Raises ValueError if any forbidden word is found.
    """
    if not do_not_use:
        return

    # Collect all text from the script
    text_fields = [
        script.hook,
        script.cta,
    ]
    for scene in script.scenes:
        text_fields.extend([
            scene.visual_description,
            scene.voiceover,
            scene.text_overlay or "",
        ])

    full_text = " ".join(text_fields).lower()

    violations = [
        word for word in do_not_use
        if word.lower() in full_text
    ]

    if violations:
        raise ValueError(
            f"Script contains forbidden words: {violations}. "
            f"Script for {script.platform}/{script.duration_seconds}s must be regenerated."
        )


def _build_script_prompt(
    brand_dna_data: dict[str, Any],
    platform: str,
    duration: int,
    aspect_ratio: str,
) -> str:
    """Build the user prompt for script generation."""
    brand_name = brand_dna_data.get("brand_name", "Unknown")
    tone = brand_dna_data.get("tone_of_voice", "")
    visual_dir = brand_dna_data.get("visual_direction", "")
    personality = ", ".join(brand_dna_data.get("brand_personality", []))
    pillars = brand_dna_data.get("messaging_pillars", [])
    do_not_use = brand_dna_data.get("do_not_use", [])
    platform_approach = brand_dna_data.get("platform_strategy", {}).get(platform, "")
    palette = brand_dna_data.get("color_palette", {})

    pillar_text = ""
    for p in pillars:
        pillar_text += f"\n  - {p.get('title', '')}: {p.get('one_liner', '')}"

    return f"""\
Generate a video script for the following:

Brand: {brand_name}
Platform: {platform}
Duration: {duration} seconds
Aspect Ratio: {aspect_ratio}

Brand Personality: {personality}
Tone of Voice: {tone}
Visual Direction: {visual_dir}
Color Palette: primary={palette.get('primary','')}, secondary={palette.get('secondary','')}, accent={palette.get('accent','')}
Platform Approach: {platform_approach}
Messaging Pillars:{pillar_text}

FORBIDDEN WORDS (do NOT use): {', '.join(do_not_use)}

Return a JSON object with these exact fields:
{{
  "hook": "First 3 seconds attention-grabbing line (max 200 chars)",
  "scenes": [
    {{
      "scene_number": 1,
      "duration_seconds": <int>,
      "visual_description": "Detailed visual description for Veo video generation — camera angle, lighting, subject, environment, color grading",
      "voiceover": "Exact narration text",
      "text_overlay": "On-screen text or null",
      "emotion": "Emotional beat (warm/urgent/aspirational/curious/etc)"
    }}
  ],
  "cta": "Platform-appropriate call-to-action (max 100 chars)"
}}

Rules:
- At least 1 scene required
- Sum of all scene durations must be ≤ {duration} seconds
- Hook must grab attention within 3 seconds
- Visual descriptions must be specific enough for AI video generation
- CTA must match {platform} conventions
- ALL content must align with the brand personality and tone

Return ONLY valid JSON. No markdown fences, no explanation.
"""


# ---------------------------------------------------------------------------
# Tool: store_scripts
# ---------------------------------------------------------------------------


async def store_scripts(
    scripts_json: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Validate and persist all generated scripts.

    Stores each VideoScript as a Firestore document, bundles them in GCS,
    creates an AgentRun record, and publishes a completion event.

    Args:
        scripts_json: JSON string of a list of VideoScript dicts.
        campaign_id: The campaign these scripts belong to.

    Returns:
        dict with status and script IDs on success.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message
        from brandforge.shared.storage import upload_blob

        scripts_data = json.loads(scripts_json)
        if isinstance(scripts_data, dict):
            scripts_data = [scripts_data]

        script_ids: list[str] = []
        for sd in scripts_data:
            script = VideoScript(**sd)
            await fs.create_document(
                collection=FIRESTORE_COLLECTION_SCRIPTS,
                doc_id=script.id,
                data=script.model_dump(mode="json"),
            )
            script_ids.append(script.id)

        # Bundle to GCS
        gcs_path = f"campaigns/{campaign_id}/scripts/scripts_bundle.json"
        await upload_blob(
            destination_path=gcs_path,
            data=json.dumps(scripts_data, indent=2).encode("utf-8"),
            content_type="application/json",
        )

        # AgentRun record
        agent_run = AgentRun(
            campaign_id=campaign_id,
            agent_name="scriptwriter",
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

        # Publish completion event
        await publish_message(
            topic=PUBSUB_TOPIC_AGENT_COMPLETE,
            message=AgentMessage(
                source_agent="scriptwriter",
                target_agent="orchestrator",
                campaign_id=campaign_id,
                event_type=EVENT_SCRIPTWRITER_COMPLETE,
                payload={
                    "script_ids": script_ids,
                    "scripts_count": len(script_ids),
                },
            ),
        )

        logger.info(
            "Stored %d scripts for campaign %s", len(script_ids), campaign_id
        )
        return {
            "status": "success",
            "script_ids": script_ids,
            "scripts_count": len(script_ids),
        }

    except Exception as exc:
        logger.error("store_scripts failed for campaign %s: %s", campaign_id, exc)
        return {"status": "error", "error": str(exc)}
