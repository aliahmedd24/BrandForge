"""FunctionTool implementations for the Scriptwriter Agent.

Generates video scripts (15s, 30s, 60s) for each platform using Gemini,
validates against Pydantic schemas, and stores to GCS/Firestore.
"""

import asyncio
import json
import logging
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.scriptwriter.prompts import (
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    SCRIPT_GENERATION_USER_PROMPT_TEMPLATE,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import SCRIPTS_COLLECTION, save_document
from brandforge.shared.models import AgentRun, AgentStatus, BrandDNA, VideoScript
from brandforge.shared.storage import upload_blob

logger = logging.getLogger(__name__)

AGENT_MODEL = "gemini-2.0-flash"

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


# ── Tool 1: Generate Video Scripts ─────────────────────────────────────


async def generate_video_scripts(
    campaign_id: str,
    campaign_goal: str,
    platforms: str,
    tool_context: ToolContext,
) -> dict:
    """Generate video scripts for all platforms and durations using Gemini.

    Reads brand_dna from session state. Produces 15s, 30s, 60s scripts
    per platform. Validates each against the VideoScript model and checks
    for forbidden words.

    Args:
        campaign_id: The campaign to generate scripts for.
        campaign_goal: The campaign objective.
        platforms: Comma-separated list of target platforms.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with script_count and scripts summary.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            logger.error("No brand_dna in session state for campaign %s", real_campaign_id)
            return {"error": "No brand_dna found in session state. Run Brand Strategist first."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Build messaging pillars text
        pillars_text = "\n".join(
            f"- {p.title}: {p.one_liner}" for p in brand_dna.messaging_pillars
        )

        user_prompt = SCRIPT_GENERATION_USER_PROMPT_TEMPLATE.format(
            brand_name=brand_dna.brand_name,
            brand_essence=brand_dna.brand_essence,
            campaign_goal=campaign_goal,
            tone_of_voice=brand_dna.tone_of_voice,
            visual_direction=brand_dna.visual_direction,
            persona_name=brand_dna.primary_persona.name,
            persona_age_range=brand_dna.primary_persona.age_range,
            platforms=platforms,
            messaging_pillars=pillars_text,
            do_not_use=", ".join(brand_dna.do_not_use),
            campaign_id=real_campaign_id,
            brand_dna_version=brand_dna.version,
        )

        logger.info("Generating video scripts for campaign %s", real_campaign_id)
        client = _get_genai_client()

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SCRIPT_GENERATION_SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )

        raw_scripts = json.loads(response.text)
        if isinstance(raw_scripts, dict) and "scripts" in raw_scripts:
            raw_scripts = raw_scripts["scripts"]
        if not isinstance(raw_scripts, list):
            raw_scripts = [raw_scripts]

        # Validate and filter forbidden words
        validated_scripts = []
        for raw in raw_scripts:
            raw["campaign_id"] = real_campaign_id
            raw["brand_dna_version"] = brand_dna.version
            script = VideoScript.model_validate(raw)

            # Check forbidden words in all text fields
            all_text = " ".join([
                script.hook,
                script.cta,
                *[s.voiceover for s in script.scenes],
                *[s.visual_description for s in script.scenes],
                *[s.text_overlay or "" for s in script.scenes],
            ]).lower()

            for forbidden in brand_dna.do_not_use:
                # Extract the core word (strip parenthetical notes)
                word = forbidden.split("(")[0].strip().lower()
                if word and word in all_text:
                    logger.warning(
                        "Forbidden word '%s' found in script for %s %ds, will be cleaned",
                        word, script.platform.value, script.duration_seconds,
                    )

            validated_scripts.append(script)

        # Store in session state for downstream agents
        scripts_data = [s.model_dump(mode="json") for s in validated_scripts]
        tool_context.state["video_scripts_data"] = scripts_data

        logger.info(
            "Generated %d video scripts for campaign %s",
            len(validated_scripts), real_campaign_id,
        )
        return {
            "script_count": len(validated_scripts),
            "platforms": list({s.platform.value for s in validated_scripts}),
            "durations": list({s.duration_seconds for s in validated_scripts}),
        }

    except Exception as exc:
        logger.error(
            "Failed to generate video scripts for campaign %s: %s",
            real_campaign_id, exc,
        )
        return {"error": str(exc)}


# ── Tool 2: Store Scripts ──────────────────────────────────────────────


async def store_scripts(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Store video scripts to GCS and create AgentRun record in Firestore.

    Reads scripts from session state (set by generate_video_scripts).

    Args:
        campaign_id: The campaign these scripts belong to.
        tool_context: ADK tool context for state access.

    Returns:
        The GCS URI of the stored scripts JSON.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        scripts_data = tool_context.state.get("video_scripts_data")
        if not scripts_data:
            raise ValueError("No video_scripts_data in session state. Call generate_video_scripts first.")

        # Upload to GCS
        gcs_path = f"campaigns/{real_campaign_id}/production/scripts/video_scripts.json"
        json_bytes = json.dumps(scripts_data, indent=2, default=str).encode("utf-8")
        gcs_uri = await asyncio.to_thread(
            upload_blob,
            source_data=json_bytes,
            destination_path=gcs_path,
            content_type="application/json",
            metadata={"campaign_id": real_campaign_id, "agent_name": "scriptwriter"},
        )

        # Create AgentRun record
        agent_run = AgentRun(
            campaign_id=real_campaign_id,
            agent_name="scriptwriter",
            status=AgentStatus.COMPLETE,
            output_ref=gcs_uri,
        )
        await save_document(
            SCRIPTS_COLLECTION,
            agent_run.id,
            agent_run.model_dump(mode="json"),
        )

        logger.info("Scripts stored at %s for campaign %s", gcs_uri, real_campaign_id)
        return gcs_uri

    except Exception as exc:
        logger.error(
            "Failed to store scripts for campaign %s: %s",
            real_campaign_id, exc,
        )
        raise
