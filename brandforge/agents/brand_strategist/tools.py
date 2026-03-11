"""FunctionTool implementations for the Brand Strategist Agent.

Each function is wrapped with ADK FunctionTool in the agent definition.
All functions are async, use ToolContext for state passing, and follow
the try/except + logging.error pattern required by CLAUDE.md.
"""

import asyncio
import json
import logging
import mimetypes
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.brand_strategist.prompts import (
    BRAND_DNA_SYSTEM_PROMPT,
    BRAND_DNA_USER_PROMPT_TEMPLATE,
    TRANSCRIPTION_PROMPT,
    VISION_ANALYSIS_PROMPT,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import (
    BRAND_DNA_COLLECTION,
    CAMPAIGNS_COLLECTION,
    query_documents,
    save_document,
    update_document,
)
from brandforge.shared.models import BrandDNA, ColorPalette, VisualAssetAnalysis
from brandforge.shared.storage import download_blob, upload_blob

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


def _mime_from_url(url: str) -> str:
    """Guess MIME type from a URL or file path.

    Returns:
        A MIME type string, defaulting to 'application/octet-stream'.
    """
    mime, _ = mimetypes.guess_type(url)
    return mime or "application/octet-stream"


def _gcs_path_from_url(url: str) -> str:
    """Extract the blob path from a gs:// URL.

    Args:
        url: A GCS URL like 'gs://bucket/path/to/file'.

    Returns:
        The path portion after the bucket name.
    """
    # gs://bucket-name/path/to/file → path/to/file
    if url.startswith("gs://"):
        parts = url[5:].split("/", 1)
        return parts[1] if len(parts) > 1 else ""
    return url


# ── Tool 1: Transcribe Voice Brief ──────────────────────────────────────


async def transcribe_voice_brief(
    voice_brief_url: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Download audio from GCS and transcribe using Gemini.

    Args:
        voice_brief_url: GCS URL of the audio file (gs://bucket/path).
        campaign_id: The campaign this brief belongs to.

    Returns:
        The transcription text. Empty string on failure or timeout.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        blob_path = _gcs_path_from_url(voice_brief_url)
        mime_type = _mime_from_url(voice_brief_url)
        if mime_type == "application/octet-stream":
            mime_type = "audio/webm"  # Default per PRD bucket structure

        logger.info(
            "Transcribing voice brief for campaign %s from %s",
            real_campaign_id, voice_brief_url,
        )
        audio_bytes = await asyncio.to_thread(download_blob, blob_path)

        client = _get_genai_client()

        async def _do_transcribe() -> str:
            """Run the Gemini transcription call."""
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=AGENT_MODEL,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    TRANSCRIPTION_PROMPT,
                ],
            )
            return response.text

        transcription = await asyncio.wait_for(_do_transcribe(), timeout=30.0)
        tool_context.state["transcription"] = transcription
        logger.info("Voice brief transcribed (%d chars)", len(transcription))
        return transcription

    except asyncio.TimeoutError:
        logger.warning(
            "Voice brief transcription timed out for campaign %s, falling back to text-only",
            campaign_id,
        )
        tool_context.state["transcription"] = ""
        return ""
    except Exception as exc:
        logger.error(
            "Failed to transcribe voice brief for campaign %s: %s",
            campaign_id, exc,
        )
        tool_context.state["transcription"] = ""
        return ""


# ── Tool 2: Analyze Brand Assets ────────────────────────────────────────


async def analyze_brand_assets(
    asset_urls: list[str],
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Download images from GCS and analyze using Gemini Vision.

    Args:
        asset_urls: List of GCS URLs for brand assets (PNG, JPEG, WEBP).
        campaign_id: The campaign these assets belong to.

    Returns:
        A dict with detected_colors, typography_style, visual_energy,
        existing_brand_elements, and recommended_direction.
    """
    default_analysis = {
        "detected_colors": [],
        "typography_style": "unknown",
        "visual_energy": "neutral",
        "existing_brand_elements": [],
        "recommended_direction": "No visual assets were analyzed.",
    }

    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        logger.info(
            "Analyzing %d brand assets for campaign %s",
            len(asset_urls), real_campaign_id,
        )

        parts: list[types.Part | str] = []
        for url in asset_urls:
            blob_path = _gcs_path_from_url(url)
            mime_type = _mime_from_url(url)
            if mime_type == "application/octet-stream":
                mime_type = "image/png"
            image_bytes = await asyncio.to_thread(download_blob, blob_path)
            parts.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )

        parts.append(VISION_ANALYSIS_PROMPT)

        client = _get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        raw = json.loads(response.text)
        analysis = VisualAssetAnalysis.model_validate(raw)
        result = analysis.model_dump()
        tool_context.state["visual_analysis"] = result
        logger.info("Brand asset analysis complete for campaign %s", campaign_id)
        return result

    except Exception as exc:
        logger.error(
            "Failed to analyze brand assets for campaign %s: %s",
            campaign_id, exc,
        )
        tool_context.state["visual_analysis"] = default_analysis
        return default_analysis


# ── Tool 3: Generate Brand DNA ──────────────────────────────────────────


def _build_fallback_dna(
    campaign_id: str,
    brand_name: str,
    product_description: str,
    target_audience: str,
    campaign_goal: str,
    tone_keywords: str,
    platforms: str,
) -> BrandDNA:
    """Build a minimal fallback BrandDNA from text brief alone.

    Returns:
        A BrandDNA instance with sensible defaults.
    """
    keyword_list = [k.strip() for k in tone_keywords.split(",") if k.strip()]
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    return BrandDNA(
        campaign_id=campaign_id,
        brand_name=brand_name,
        brand_essence=f"{brand_name}: {campaign_goal} for {target_audience}.",
        brand_personality=keyword_list[:5] or ["authentic", "bold", "modern", "trustworthy", "creative"],
        tone_of_voice=f"A voice that is {', '.join(keyword_list[:3] or ['professional', 'approachable', 'clear'])}.",
        color_palette=ColorPalette(
            primary="#1A1A2E", secondary="#16213E",
            accent="#0F3460", background="#F5F5F5", text="#1A1A1A",
        ),
        typography=dict(
            heading_font="Inter Display",
            body_font="Inter",
            font_personality="Clean and modern sans-serif",
        ),
        primary_persona=dict(
            name=target_audience,
            age_range="25-45",
            values=keyword_list[:3] or ["quality"],
            pain_points=["Finding authentic brands"],
            content_habits=["Social media browsing"],
        ),
        messaging_pillars=[
            dict(
                title="Core Value",
                one_liner=f"{brand_name} delivers {campaign_goal}.",
                supporting_points=[product_description],
                avoid=["Generic claims"],
            ),
        ],
        visual_direction=f"Visual style reflecting {', '.join(keyword_list[:3] or ['modern'])} aesthetics.",
        platform_strategy={p: f"Tailored {campaign_goal} content" for p in platform_list},
        do_not_use=["generic", "best-in-class", "synergy"],
        source_brief_summary=f"Brand: {brand_name}. Product: {product_description}. Goal: {campaign_goal}.",
    )


async def generate_brand_dna(
    campaign_id: str,
    brand_name: str,
    product_description: str,
    target_audience: str,
    campaign_goal: str,
    tone_keywords: str,
    platforms: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a complete Brand DNA document using Gemini structured output.

    Reads transcription and visual analysis from session state if available.
    Falls back to a minimal Brand DNA if the Gemini call fails.

    Args:
        campaign_id: The campaign to generate DNA for.
        brand_name: The brand name.
        product_description: Description of the product/service.
        target_audience: Target audience description.
        campaign_goal: The campaign objective.
        tone_keywords: Comma-separated tone keywords.
        platforms: Comma-separated target platforms.

    Returns:
        A dict representation of the validated BrandDNA model.
    """
    # Always use the real campaign_id from session state — the LLM may hallucinate a slug.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        transcription = tool_context.state.get("transcription", "")
        visual_analysis = tool_context.state.get("visual_analysis", None)

        visual_str = json.dumps(visual_analysis) if visual_analysis else "No visual assets provided."

        user_prompt = BRAND_DNA_USER_PROMPT_TEMPLATE.format(
            brand_name=brand_name,
            product_description=product_description,
            target_audience=target_audience,
            campaign_goal=campaign_goal,
            tone_keywords=tone_keywords,
            platforms=platforms,
            transcription=transcription or "No voice brief provided.",
            visual_analysis=visual_str,
        )

        logger.info("Generating Brand DNA for campaign %s", real_campaign_id)
        client = _get_genai_client()

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=BRAND_DNA_SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )

        raw = json.loads(response.text)

        # Inject/fix fields the LLM often omits or gets wrong before validation.
        raw["campaign_id"] = real_campaign_id
        raw.setdefault("typography", {
            "heading_font": "Inter Display",
            "body_font": "Inter",
            "font_personality": "Clean and modern",
        })
        raw.setdefault("primary_persona", {
            "name": target_audience or "General audience",
            "age_range": "25-45",
            "values": ["quality"],
            "pain_points": ["Finding the right product"],
            "content_habits": ["Social media browsing"],
        })
        raw.setdefault("visual_direction", f"Modern visual style reflecting {brand_name} brand identity.")
        # Ensure messaging_pillars items each have an 'avoid' list
        for pillar in raw.get("messaging_pillars", []):
            if isinstance(pillar, dict):
                pillar.setdefault("avoid", ["Generic claims"])
        # Convert platform_strategy from list to dict if LLM returns a list
        ps = raw.get("platform_strategy")
        if isinstance(ps, list):
            raw["platform_strategy"] = {
                item.get("platform_name", item.get("platform", f"platform_{i}")): item.get("strategy", item.get("content_approach", str(item)))
                for i, item in enumerate(ps)
                if isinstance(item, dict)
            }
        elif not isinstance(ps, dict):
            platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
            raw["platform_strategy"] = {p: "Tailored content" for p in platform_list}

        brand_dna = BrandDNA.model_validate(raw)

        brand_dna.source_brief_summary = (
            f"Brand: {brand_name}. Product: {product_description}. "
            f"Goal: {campaign_goal}."
        )

        result = brand_dna.model_dump(mode="json")
        tool_context.state["brand_dna"] = result
        logger.info("Brand DNA generated for campaign %s", real_campaign_id)
        return result

    except Exception as exc:
        logger.error(
            "Gemini Brand DNA generation failed for campaign %s: %s. Using fallback.",
            real_campaign_id, exc,
        )
        fallback = _build_fallback_dna(
            real_campaign_id, brand_name, product_description,
            target_audience, campaign_goal, tone_keywords, platforms,
        )
        result = fallback.model_dump(mode="json")
        tool_context.state["brand_dna"] = result
        return result


# ── Tool 4: Store Brand DNA ─────────────────────────────────────────────


async def store_brand_dna(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Store Brand DNA in Firestore and GCS. Update Campaign document.

    Reads the brand_dna from session state (set by generate_brand_dna).
    Handles version incrementing: queries existing DNA docs for this campaign
    and sets version to max_existing + 1.

    Args:
        campaign_id: The campaign this DNA belongs to.

    Returns:
        The brand_dna document ID string.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            raise ValueError("No brand_dna found in session state. Call generate_brand_dna first.")

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Ensure brand_dna uses the real campaign_id
        brand_dna.campaign_id = real_campaign_id

        # Version incrementing
        try:
            existing = await query_documents(
                BRAND_DNA_COLLECTION,
                field="campaign_id",
                value=real_campaign_id,
                order_by="version",
                descending=True,
                limit=1,
            )
            if existing:
                brand_dna.version = existing[0]["version"] + 1
                logger.info(
                    "Incrementing BrandDNA version to %d for campaign %s",
                    brand_dna.version, real_campaign_id,
                )
        except Exception as query_exc:
            logger.warning(
                "Could not query existing BrandDNA versions for campaign %s: %s. Defaulting to v1.",
                real_campaign_id, query_exc,
            )

        doc_data = brand_dna.model_dump(mode="json")

        # Save to Firestore
        await save_document(BRAND_DNA_COLLECTION, brand_dna.id, doc_data)

        # Save to GCS
        gcs_path = f"campaigns/{real_campaign_id}/brand_dna/brand_kit.json"
        json_bytes = brand_dna.model_dump_json(indent=2).encode("utf-8")
        await asyncio.to_thread(
            upload_blob,
            source_data=json_bytes,
            destination_path=gcs_path,
            content_type="application/json",
        )

        # Update Campaign document
        await update_document(
            CAMPAIGNS_COLLECTION,
            real_campaign_id,
            {"brand_dna_id": brand_dna.id},
        )

        # Store structured result in session state for downstream agents
        tool_context.state["brand_dna_result"] = brand_dna.model_dump_json()
        tool_context.state["brand_dna"] = doc_data  # Update with final version

        logger.info(
            "Brand DNA v%d stored (id=%s) for campaign %s",
            brand_dna.version, brand_dna.id, real_campaign_id,
        )
        return brand_dna.id

    except Exception as exc:
        logger.error(
            "Failed to store Brand DNA for campaign %s: %s",
            real_campaign_id, exc,
        )
        raise
