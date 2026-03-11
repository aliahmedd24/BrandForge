"""FunctionTool implementations for the Competitor Intelligence Agent.

Uses Playwright for screenshot capture and Gemini Vision for structured
brand analysis. Generates a competitive positioning map as SVG.
"""

import asyncio
import json
import logging
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.competitor_intel.prompts import (
    POSITIONING_MAP_PROMPT,
    VISION_ANALYSIS_PROMPT,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import COMPETITOR_MAPS_COLLECTION, save_document
from brandforge.shared.models import CompetitorMap, CompetitorProfile
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


# ── Tool 1: Capture Competitor Screenshot ──────────────────────────────


async def capture_competitor_screenshot(
    url: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Capture a screenshot of a competitor URL using Playwright.

    Saves the screenshot as JPEG to GCS. Gracefully handles inaccessible
    URLs by returning an empty string.

    Args:
        url: The competitor website URL to capture.
        campaign_id: The campaign this screenshot belongs to.

    Returns:
        GCS URL of the screenshot, or empty string on failure.
    """
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        logger.info("Capturing screenshot of %s", url)

        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 900})

            try:
                response = await page.goto(url, timeout=30000, wait_until="networkidle")
                if response and response.status >= 400:
                    logger.warning(
                        "Competitor URL %s returned status %d, skipping",
                        url, response.status,
                    )
                    await browser.close()
                    return ""
            except Exception as nav_exc:
                logger.warning(
                    "Could not navigate to %s: %s, skipping", url, nav_exc
                )
                await browser.close()
                return ""

            screenshot_bytes = await page.screenshot(
                type="jpeg", quality=85, full_page=False
            )
            await browser.close()

        # Upload to GCS
        safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_")[:80]
        gcs_path = f"campaigns/{real_campaign_id}/competitors/{safe_name}.jpg"
        gcs_url = await asyncio.to_thread(
            upload_blob,
            source_data=screenshot_bytes,
            destination_path=gcs_path,
            content_type="image/jpeg",
        )

        logger.info("Screenshot saved to %s", gcs_url)
        return gcs_url

    except Exception as exc:
        logger.error("Failed to capture screenshot of %s: %s", url, exc)
        return ""


# ── Tool 2: Analyze Competitor Brand ───────────────────────────────────


async def analyze_competitor_brand(
    screenshot_gcs_url: str,
    competitor_url: str,
    tool_context: ToolContext,
) -> dict:
    """Analyze a competitor brand screenshot using Gemini Vision.

    Extracts structured brand data: visual style, colors, tone, positioning.

    Args:
        screenshot_gcs_url: GCS URL of the competitor screenshot.
        competitor_url: The original competitor website URL.

    Returns:
        A CompetitorProfile dict, or empty dict on failure.
    """
    try:
        from brandforge.shared.storage import download_blob

        logger.info("Analyzing competitor: %s", competitor_url)

        # Download screenshot from GCS
        blob_path = screenshot_gcs_url.replace(f"gs://{settings.gcs_bucket}/", "")
        image_bytes = await asyncio.to_thread(download_blob, blob_path)

        client = _get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                VISION_ANALYSIS_PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        raw = json.loads(response.text)
        raw["competitor_url"] = competitor_url
        raw["screenshot_gcs_url"] = screenshot_gcs_url

        profile = CompetitorProfile.model_validate(raw)
        profile_dict = profile.model_dump(mode="json")

        # Append to competitors list in state
        competitors = tool_context.state.get("competitor_profiles", [])
        competitors.append(profile_dict)
        tool_context.state["competitor_profiles"] = competitors

        logger.info(
            "Competitor analysis complete: %s (style=%s)",
            profile.brand_name, profile.visual_style,
        )
        return profile_dict

    except Exception as exc:
        logger.error(
            "Failed to analyze competitor %s: %s", competitor_url, exc
        )
        return {}


# ── Tool 3: Generate Competitor Map ────────────────────────────────────


async def generate_competitor_map(
    campaign_id: str,
    brand_name: str,
    industry: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a competitive positioning map with differentiation strategy.

    Reads competitor_profiles from session state, generates a 2×2 quadrant
    SVG positioning chart, and stores the CompetitorMap in Firestore.

    Args:
        campaign_id: The campaign this map belongs to.
        brand_name: The user's brand name.
        industry: The brand's industry.

    Returns:
        A CompetitorMap dict with SVG positioning chart.
    """
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        competitors_raw = tool_context.state.get("competitor_profiles", [])

        if not competitors_raw:
            logger.info("No competitor profiles to map, skipping")
            return {}

        competitors = [CompetitorProfile.model_validate(c) for c in competitors_raw]

        # Generate positioning map and strategy via Gemini
        client = _get_genai_client()
        prompt = POSITIONING_MAP_PROMPT.format(
            competitor_data=json.dumps(competitors_raw, indent=2),
            brand_name=brand_name,
            industry=industry,
        )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        raw = json.loads(response.text)

        competitor_map = CompetitorMap(
            campaign_id=real_campaign_id,
            competitors=competitors,
            user_brand_positioning=raw.get("user_brand_positioning", {
                "mainstream_niche_score": 0.5,
                "premium_accessible_score": 0.5,
            }),
            differentiation_strategy=raw.get(
                "differentiation_strategy",
                "Focus on unique brand values and authentic storytelling.",
            ),
            positioning_map_svg=raw.get(
                "positioning_map_svg",
                _build_fallback_svg(competitors, brand_name),
            ),
        )

        map_dict = competitor_map.model_dump(mode="json")

        # Store in Firestore
        try:
            await save_document(
                COMPETITOR_MAPS_COLLECTION, competitor_map.id, map_dict
            )
            logger.info("Competitor map stored (id=%s)", competitor_map.id)
        except Exception as store_exc:
            logger.warning("Failed to store competitor map: %s", store_exc)

        # Inject into session state for Brand Strategist
        tool_context.state["competitor_map"] = map_dict
        logger.info(
            "Competitor map generated: %d competitors, strategy=%s...",
            len(competitors), competitor_map.differentiation_strategy[:60],
        )
        return map_dict

    except Exception as exc:
        logger.error("Failed to generate competitor map: %s", exc)
        return {}


def _build_fallback_svg(
    competitors: list[CompetitorProfile],
    brand_name: str,
) -> str:
    """Build a simple SVG 2×2 positioning chart as fallback.

    Args:
        competitors: List of analyzed competitor profiles.
        brand_name: The user's brand name.

    Returns:
        SVG string of the positioning chart.
    """
    svg_parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">',
        '<rect width="400" height="400" fill="#0A0A0F"/>',
        # Axes
        '<line x1="200" y1="20" x2="200" y2="380" stroke="#333" stroke-width="1"/>',
        '<line x1="20" y1="200" x2="380" y2="200" stroke="#333" stroke-width="1"/>',
        # Labels
        '<text x="200" y="15" fill="#8B8BA3" text-anchor="middle" font-size="11">Premium</text>',
        '<text x="200" y="395" fill="#8B8BA3" text-anchor="middle" font-size="11">Accessible</text>',
        '<text x="15" y="205" fill="#8B8BA3" text-anchor="start" font-size="11" transform="rotate(-90,15,205)">Mainstream</text>',
        '<text x="390" y="205" fill="#8B8BA3" text-anchor="end" font-size="11" transform="rotate(-90,390,205)">Niche</text>',
    ]

    # Competitor dots
    colors = ["#EF4444", "#F59E0B", "#8B5CF6"]
    for i, comp in enumerate(competitors[:3]):
        x = 20 + comp.mainstream_niche_score * 360
        y = 380 - comp.premium_accessible_score * 360
        color = colors[i % 3]
        svg_parts.append(
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="8" fill="{color}" opacity="0.8"/>'
        )
        svg_parts.append(
            f'<text x="{x:.0f}" y="{y - 12:.0f}" fill="{color}" text-anchor="middle" '
            f'font-size="10">{comp.brand_name[:15]}</text>'
        )

    # User brand dot (distinct green)
    svg_parts.append('<circle cx="200" cy="200" r="10" fill="#10B981" opacity="0.9"/>')
    svg_parts.append(
        f'<text x="200" y="185" fill="#10B981" text-anchor="middle" '
        f'font-size="11" font-weight="bold">{brand_name[:15]}</text>'
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)
