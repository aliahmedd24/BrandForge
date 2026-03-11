"""FunctionTool implementations for the Brand Memory Agent.

Manages persistent brand intelligence in Firestore. Supports fetch,
update (append-only for history), and memory-based recommendation
application for new campaigns.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.brand_memory.prompts import MEMORY_SYNTHESIS_PROMPT
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import (
    BRAND_MEMORY_COLLECTION,
    get_document,
    query_documents,
    save_document,
    update_document,
)
from brandforge.shared.models import (
    BrandMemory,
    CampaignPerformanceSummary,
    CreativeRecommendation,
)

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


# ── Tool 1: Fetch Brand Memory ────────────────────────────────────────


async def fetch_brand_memory(
    brand_name: str,
    tool_context: ToolContext,
) -> dict:
    """Fetch existing brand memory from Firestore.

    If no memory exists for this brand, returns an empty dict indicating
    this is a first-run brand.

    Args:
        brand_name: The brand name to look up.

    Returns:
        A BrandMemory dict if found, or empty dict for first-run brands.
    """
    try:
        logger.info("Fetching brand memory for: %s", brand_name)

        # Query by brand_name
        results = await query_documents(
            BRAND_MEMORY_COLLECTION,
            field="brand_name",
            value=brand_name,
            limit=1,
        )

        if results:
            memory = BrandMemory.model_validate(results[0])
            memory_dict = memory.model_dump(mode="json")
            tool_context.state["brand_memory"] = memory_dict
            tool_context.state["brand_memory_id"] = memory.id
            logger.info(
                "Brand memory found: %d past campaigns, avg score %.2f",
                memory.campaign_count, memory.avg_brand_coherence_score,
            )
            return memory_dict

        logger.info("No brand memory found for %s — first campaign", brand_name)
        tool_context.state["brand_memory"] = {}
        return {}

    except Exception as exc:
        logger.error("Failed to fetch brand memory for %s: %s", brand_name, exc)
        tool_context.state["brand_memory"] = {}
        return {}


# ── Tool 2: Apply Memory Recommendations ──────────────────────────────


async def apply_memory_recommendations(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Apply brand memory recommendations to the current campaign context.

    Reads brand memory from session state and injects recommendations
    into the campaign context for Brand Strategist consumption.

    Args:
        campaign_id: The current campaign ID.

    Returns:
        A dict with applied recommendations and pre-populated preferences.
    """
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        memory_dict = tool_context.state.get("brand_memory", {})
        if not memory_dict:
            logger.info("No brand memory to apply for campaign %s", real_campaign_id)
            return {"applied": False, "reason": "first_campaign"}

        memory = BrandMemory.model_validate(memory_dict)

        # Build recommendation context for Brand Strategist
        recommendations = {
            "applied": True,
            "campaign_count": memory.campaign_count,
            "content_type_bias": memory.content_type_bias,
            "platform_priority": [p.value if hasattr(p, "value") else p for p in memory.platform_priority],
            "avg_brand_coherence_score": memory.avg_brand_coherence_score,
            "recommendations": [
                r.model_dump(mode="json") if hasattr(r, "model_dump") else r
                for r in memory.next_campaign_recommendations
            ],
        }

        # If evolved palette exists, suggest it
        if memory.evolved_color_palette:
            recommendations["suggested_color_palette"] = (
                memory.evolved_color_palette.model_dump(mode="json")
                if hasattr(memory.evolved_color_palette, "model_dump")
                else memory.evolved_color_palette
            )

        # Store in session state for Brand Strategist
        tool_context.state["memory_recommendations"] = recommendations
        logger.info(
            "Applied memory recommendations for campaign %s: %d recs, bias=%s",
            real_campaign_id, len(recommendations.get("recommendations", [])),
            recommendations["content_type_bias"],
        )
        return recommendations

    except Exception as exc:
        logger.error(
            "Failed to apply memory recommendations for %s: %s",
            real_campaign_id, exc,
        )
        return {"applied": False, "reason": str(exc)}


# ── Tool 3: Update Brand Memory ───────────────────────────────────────


async def update_brand_memory(
    brand_name: str,
    campaign_id: str,
    brand_coherence_score: float,
    top_performing_asset_type: str,
    top_performing_platform: str,
    top_performing_tone: str,
    brand_dna_id: str,
    tool_context: ToolContext,
) -> dict:
    """Update brand memory with new campaign performance data.

    Appends a CampaignPerformanceSummary to the brand's history.
    Creates a new BrandMemory document if this is the first campaign.
    Uses Gemini to synthesize updated recommendations.

    Args:
        brand_name: The brand name.
        campaign_id: The completed campaign ID.
        brand_coherence_score: The campaign's QA coherence score.
        top_performing_asset_type: "video" or "image".
        top_performing_platform: Best performing platform name.
        top_performing_tone: The tone that performed best.
        brand_dna_id: The BrandDNA document ID used.

    Returns:
        The updated BrandMemory dict.
    """
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        # Build performance summary
        brand_dna = tool_context.state.get("brand_dna", {})
        color_palette = brand_dna.get("color_palette", {
            "primary": "#1A1A2E", "secondary": "#16213E",
            "accent": "#0F3460", "background": "#F5F5F5", "text": "#1A1A1A",
        })

        performance = CampaignPerformanceSummary(
            campaign_id=real_campaign_id,
            brand_coherence_score=brand_coherence_score,
            top_performing_asset_type=top_performing_asset_type,
            top_performing_platform=top_performing_platform,
            top_performing_tone=top_performing_tone,
            winning_color_palette=color_palette,
            audience_response_patterns=[],
            recommendations_applied=[],
        )

        # Fetch or create brand memory
        memory_dict = tool_context.state.get("brand_memory", {})
        memory_id = tool_context.state.get("brand_memory_id")

        if memory_dict and memory_id:
            memory = BrandMemory.model_validate(memory_dict)
        else:
            # First campaign — create new memory
            memory = BrandMemory(
                brand_name=brand_name,
                current_brand_dna_id=brand_dna_id,
            )
            memory_id = memory.id

        # Append-only: add new performance summary
        memory.campaign_history.append(performance)
        memory.campaign_count = len(memory.campaign_history)
        memory.current_brand_dna_id = brand_dna_id

        # Update rolling average
        scores = [c.brand_coherence_score for c in memory.campaign_history]
        memory.avg_brand_coherence_score = sum(scores) / len(scores)

        # Use Gemini to synthesize updated recommendations
        try:
            client = _get_genai_client()
            history_data = [
                c.model_dump(mode="json") for c in memory.campaign_history
            ]
            prompt = MEMORY_SYNTHESIS_PROMPT.format(
                campaign_history=json.dumps(history_data, indent=2),
                current_bias=json.dumps(memory.content_type_bias),
                current_priority=json.dumps(
                    [p.value if hasattr(p, "value") else p for p in memory.platform_priority]
                ),
            )

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=AGENT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )

            synthesis = json.loads(response.text)
            memory.content_type_bias = synthesis.get(
                "content_type_bias", memory.content_type_bias
            )

            priority_raw = synthesis.get("platform_priority", [])
            from brandforge.shared.models import Platform
            memory.platform_priority = []
            for p in priority_raw:
                try:
                    memory.platform_priority.append(Platform(p))
                except ValueError:
                    pass

            recs_raw = synthesis.get("recommendations", [])
            memory.next_campaign_recommendations = []
            for r in recs_raw:
                try:
                    memory.next_campaign_recommendations.append(
                        CreativeRecommendation.model_validate(r)
                    )
                except Exception:
                    pass

        except Exception as synth_exc:
            logger.warning("Gemini synthesis failed, using rule-based update: %s", synth_exc)
            # Rule-based fallback for content type bias
            video_campaigns = sum(
                1 for c in memory.campaign_history
                if c.top_performing_asset_type == "video"
            )
            total = len(memory.campaign_history)
            memory.content_type_bias = {
                "video": video_campaigns / total if total else 0.5,
                "image": (total - video_campaigns) / total if total else 0.5,
            }

        memory.updated_at = datetime.now(timezone.utc)
        memory_data = memory.model_dump(mode="json")

        # Save to Firestore
        await save_document(BRAND_MEMORY_COLLECTION, memory_id, memory_data)
        tool_context.state["brand_memory"] = memory_data
        tool_context.state["brand_memory_id"] = memory_id

        logger.info(
            "Brand memory updated for %s: %d campaigns, avg score %.2f",
            brand_name, memory.campaign_count, memory.avg_brand_coherence_score,
        )
        return memory_data

    except Exception as exc:
        logger.error("Failed to update brand memory for %s: %s", brand_name, exc)
        return {}
