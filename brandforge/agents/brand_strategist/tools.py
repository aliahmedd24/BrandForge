"""Brand Strategist tool implementations.

All business logic for the Brand Strategist agent lives here.
agent.py stays thin — only the LlmAgent definition.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from google import genai
from google.genai import types

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_BRAND_DNA,
    FIRESTORE_COLLECTION_CAMPAIGNS,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    BrandDNA,
    VisualAssetAnalysis,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TRANSCRIPTION_TIMEOUT_SECONDS = 30

_BRAND_DNA_SYSTEM_PROMPT = """\
You are an elite brand strategist with 20 years of experience at world-class
creative agencies. You analyze brand briefs with surgical precision.

Your output MUST be grounded exclusively in the provided inputs.
Do not invent attributes, audiences, or directions not evidenced by the brief.

You will produce a complete Brand DNA in the exact JSON schema provided.
Every field is required. Be specific, not generic.

BAD: tone_of_voice: "friendly and professional"
GOOD: tone_of_voice: "Direct and quietly confident. Speaks like an expert friend,
not a brand. Uses concrete specifics over abstract claims. Never uses superlatives."
"""

_VISUAL_ANALYSIS_PROMPT = """\
You are a brand visual analyst. Analyze the provided brand asset images and
return a JSON object with exactly these fields:
{
  "detected_colors": ["#RRGGBB", ...],   // Up to 8 dominant hex colors
  "typography_style": "...",              // Describe detected typeface style
  "visual_energy": "...",                 // e.g. "minimalist", "maximalist", "editorial"
  "existing_brand_elements": ["..."],     // Logos, icons, patterns detected
  "recommended_direction": "..."          // Visual direction recommendation
}

Return ONLY valid JSON. No markdown fences, no explanation.
"""


# ---------------------------------------------------------------------------
# Tool: transcribe_voice_brief
# ---------------------------------------------------------------------------


async def transcribe_voice_brief(
    voice_brief_url: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Transcribe a spoken voice brief from GCS into text.

    Downloads the audio file from GCS and sends it to Gemini for
    transcription. Times out after 30 seconds with a graceful fallback.

    Args:
        voice_brief_url: GCS URI of the audio file (gs://bucket/path).
        campaign_id: The campaign this brief belongs to.

    Returns:
        dict with status ("success"/"error") and transcription or error message.
    """
    try:
        from brandforge.shared.storage import download_blob

        # Strip gs://bucket/ prefix to get the blob path
        blob_path = _gcs_uri_to_blob_path(voice_brief_url)
        audio_bytes = await asyncio.wait_for(
            download_blob(blob_path),
            timeout=_TRANSCRIPTION_TIMEOUT_SECONDS,
        )

        config = get_config()
        client = genai.Client(vertexai=True, project=config.gcp_project_id, location=config.gcp_region)

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/webm")
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=config.gemini_model,
                contents=[
                    "Transcribe the following audio recording verbatim. "
                    "Return only the transcription text, nothing else.",
                    audio_part,
                ],
            ),
            timeout=_TRANSCRIPTION_TIMEOUT_SECONDS,
        )

        transcription = response.text.strip()
        logger.info(
            "Transcribed voice brief for campaign %s (%d chars)",
            campaign_id,
            len(transcription),
        )
        return {"status": "success", "transcription": transcription}

    except TimeoutError:
        logger.warning(
            "Voice brief transcription timed out for campaign %s", campaign_id
        )
        return {
            "status": "error",
            "error": "Voice brief transcription timed out (30s limit). "
            "Proceeding with text-only brief.",
        }
    except Exception as exc:
        logger.error(
            "Voice brief transcription failed for campaign %s: %s",
            campaign_id,
            exc,
        )
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: analyze_brand_assets
# ---------------------------------------------------------------------------


async def analyze_brand_assets(
    asset_urls: list[str],
    campaign_id: str,
) -> dict[str, Any]:
    """Analyze uploaded brand asset images using Gemini Vision.

    Downloads images from GCS, sends them to Gemini Vision for analysis,
    and returns a structured VisualAssetAnalysis.

    Args:
        asset_urls: List of GCS URIs for uploaded images.
        campaign_id: The campaign these assets belong to.

    Returns:
        dict with status and VisualAssetAnalysis data or error message.
    """
    try:
        from brandforge.shared.storage import download_blob

        # Download all images
        image_parts: list[types.Part] = []
        for url in asset_urls:
            blob_path = _gcs_uri_to_blob_path(url)
            image_bytes = await download_blob(blob_path)
            mime_type = _guess_mime_type(blob_path)
            image_parts.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )

        config = get_config()
        client = genai.Client(vertexai=True, project=config.gcp_project_id, location=config.gcp_region)

        contents: list[Any] = [_VISUAL_ANALYSIS_PROMPT, *image_parts]

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=config.gemini_model,
            contents=contents,
        )

        raw_text = response.text.strip()
        # Strip markdown fences if model includes them
        raw_text = _strip_json_fences(raw_text)
        analysis_data = json.loads(raw_text)
        analysis = VisualAssetAnalysis(**analysis_data)

        logger.info(
            "Analyzed %d brand assets for campaign %s", len(asset_urls), campaign_id
        )
        return {"status": "success", "data": analysis.model_dump()}

    except Exception as exc:
        logger.error(
            "Brand asset analysis failed for campaign %s: %s", campaign_id, exc
        )
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: generate_brand_dna
# ---------------------------------------------------------------------------


async def generate_brand_dna(
    brand_name: str,
    product_description: str,
    target_audience: str,
    campaign_goal: str,
    tone_keywords: str,
    platforms: str,
    campaign_id: str,
    transcription: str = "",
    visual_analysis: str = "",
) -> dict[str, Any]:
    """Generate a structured Brand DNA document using Gemini.

    Synthesises all brief inputs (text, transcription, visual analysis) into
    a complete BrandDNA Pydantic model. Uses JSON-mode prompting with
    post-generation Pydantic validation.

    Args:
        brand_name: The brand name.
        product_description: What the product does.
        target_audience: Primary target audience.
        campaign_goal: Campaign objective.
        tone_keywords: Comma-separated tone adjectives.
        platforms: Comma-separated target platforms.
        campaign_id: The campaign ID.
        transcription: Voice brief transcription (empty if none).
        visual_analysis: JSON string of VisualAssetAnalysis (empty if none).

    Returns:
        dict with status and BrandDNA data or error message.
    """
    try:
        user_prompt = _build_brand_dna_user_prompt(
            brand_name=brand_name,
            product_description=product_description,
            target_audience=target_audience,
            campaign_goal=campaign_goal,
            tone_keywords=tone_keywords,
            platforms=platforms,
            transcription=transcription,
            visual_analysis=visual_analysis,
        )

        config = get_config()
        client = genai.Client(vertexai=True, project=config.gcp_project_id, location=config.gcp_region)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=config.gemini_model,
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=_BRAND_DNA_SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )

        raw_text = response.text.strip()
        raw_text = _strip_json_fences(raw_text)
        brand_dna_data = json.loads(raw_text)

        # Inject campaign_id and generate id
        brand_dna_data["campaign_id"] = campaign_id
        if "id" not in brand_dna_data:
            brand_dna_data["id"] = str(uuid.uuid4())

        brand_dna = BrandDNA(**brand_dna_data)
        logger.info(
            "Generated Brand DNA for '%s' (campaign %s)", brand_name, campaign_id
        )
        return {"status": "success", "data": brand_dna.model_dump(mode="json")}

    except Exception as exc:
        logger.error(
            "Brand DNA generation failed for campaign %s: %s", campaign_id, exc
        )
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: store_brand_dna
# ---------------------------------------------------------------------------


async def store_brand_dna(
    brand_dna_json: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Persist Brand DNA to Firestore and GCS, then notify via Pub/Sub.

    Stores the BrandDNA document in:
      1. Firestore: /brand_dna/{id}
      2. GCS: campaigns/{campaign_id}/brand_dna/brand_kit.json
    Updates the Campaign document with brand_dna_id.
    Publishes a 'brand_dna_ready' event to Pub/Sub.
    Handles version incrementing — queries for existing versions.

    Args:
        brand_dna_json: JSON string of the BrandDNA model.
        campaign_id: The campaign this Brand DNA belongs to.

    Returns:
        dict with status and brand_dna_id or error message.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message
        from brandforge.shared.storage import upload_blob

        brand_dna_data = json.loads(brand_dna_json)

        # Version increment: check for existing Brand DNA on this campaign
        existing_docs = await fs.query_collection(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            field="campaign_id",
            op="==",
            value=campaign_id,
        )
        if existing_docs:
            max_version = max(doc.get("version", 1) for doc in existing_docs)
            brand_dna_data["version"] = max_version + 1

        brand_dna = BrandDNA(**brand_dna_data)

        # 1. Store in Firestore
        await fs.create_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            doc_id=brand_dna.id,
            data=brand_dna.model_dump(mode="json"),
        )

        # 2. Store in GCS
        gcs_path = f"campaigns/{campaign_id}/brand_dna/brand_kit_v{brand_dna.version}.json"
        await upload_blob(
            destination_path=gcs_path,
            data=json.dumps(brand_dna.model_dump(mode="json"), indent=2).encode("utf-8"),
            content_type="application/json",
        )

        # 3. Update Campaign document
        await fs.update_document(
            collection=FIRESTORE_COLLECTION_CAMPAIGNS,
            doc_id=campaign_id,
            updates={"brand_dna_id": brand_dna.id},
        )

        # 4. Publish Pub/Sub notification
        await publish_message(
            topic=PUBSUB_TOPIC_AGENT_COMPLETE,
            message=AgentMessage(
                source_agent="brand_strategist",
                target_agent="orchestrator",
                campaign_id=campaign_id,
                event_type="brand_dna_ready",
                payload={"brand_dna_id": brand_dna.id, "version": brand_dna.version},
            ),
        )

        logger.info(
            "Stored Brand DNA %s v%d for campaign %s",
            brand_dna.id,
            brand_dna.version,
            campaign_id,
        )
        return {
            "status": "success",
            "brand_dna_id": brand_dna.id,
            "version": brand_dna.version,
        }

    except Exception as exc:
        logger.error(
            "store_brand_dna failed for campaign %s: %s", campaign_id, exc
        )
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------


def _gcs_uri_to_blob_path(gcs_uri: str) -> str:
    """Convert a gs://bucket/path URI to just the blob path.

    Args:
        gcs_uri: Full GCS URI, e.g. 'gs://brandforge-assets/campaigns/abc/voice.webm'.

    Returns:
        The blob path after the bucket name, e.g. 'campaigns/abc/voice.webm'.
    """
    if gcs_uri.startswith("gs://"):
        parts = gcs_uri[5:].split("/", 1)
        return parts[1] if len(parts) > 1 else ""
    return gcs_uri


def _guess_mime_type(blob_path: str) -> str:
    """Guess MIME type from file extension.

    Args:
        blob_path: The GCS blob path.

    Returns:
        MIME type string.
    """
    lower = blob_path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def _strip_json_fences(text: str) -> str:
    """Remove markdown JSON code fences if present.

    Args:
        text: Raw text possibly wrapped in ```json ... ```.

    Returns:
        Clean JSON string.
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _build_brand_dna_user_prompt(
    brand_name: str,
    product_description: str,
    target_audience: str,
    campaign_goal: str,
    tone_keywords: str,
    platforms: str,
    transcription: str,
    visual_analysis: str,
) -> str:
    """Build the user prompt for Brand DNA generation.

    Args:
        brand_name: The brand name.
        product_description: Product description.
        target_audience: Target audience.
        campaign_goal: Campaign goal.
        tone_keywords: Comma-separated tone keywords.
        platforms: Comma-separated platforms.
        transcription: Voice brief transcription (may be empty).
        visual_analysis: Visual analysis JSON string (may be empty).

    Returns:
        Formatted user prompt string.
    """
    prompt = f"""\
Brand Brief:
- Name: {brand_name}
- Product: {product_description}
- Audience: {target_audience}
- Goal: {campaign_goal}
- Tone Keywords: {tone_keywords}
- Platforms: {platforms}
"""

    if transcription:
        prompt += f"\nVoice Brief Transcription:\n{transcription}\n"
    else:
        prompt += "\nVoice Brief Transcription: (none provided)\n"

    if visual_analysis:
        prompt += f"\nVisual Asset Analysis:\n{visual_analysis}\n"
    else:
        prompt += "\nVisual Asset Analysis: (no assets uploaded)\n"

    prompt += """
Generate the complete Brand DNA as a JSON object with these exact fields:
{
  "brand_name": "...",
  "brand_essence": "One-sentence brand soul",
  "brand_personality": ["adj1", "adj2", "adj3", "adj4", "adj5"],
  "tone_of_voice": "Detailed tone paragraph",
  "color_palette": {
    "primary": "#RRGGBB",
    "secondary": "#RRGGBB",
    "accent": "#RRGGBB",
    "background": "#RRGGBB",
    "text": "#RRGGBB"
  },
  "typography": {
    "heading_font": "...",
    "body_font": "...",
    "font_personality": "..."
  },
  "primary_persona": {
    "name": "...",
    "age_range": "...",
    "values": ["..."],
    "pain_points": ["..."],
    "content_habits": ["..."]
  },
  "messaging_pillars": [
    {
      "title": "...",
      "one_liner": "...",
      "supporting_points": ["..."],
      "avoid": ["..."]
    }
  ],
  "visual_direction": "Paragraph for image/video agents",
  "platform_strategy": {"platform_name": "content approach"},
  "competitor_insights": [],
  "do_not_use": ["forbidden words/themes"],
  "source_brief_summary": "Summary of what inputs were provided"
}

Return ONLY valid JSON. No markdown fences, no explanation.
"""
    return prompt
