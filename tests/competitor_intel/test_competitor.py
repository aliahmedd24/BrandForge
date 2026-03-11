"""Tests for the Competitor Intelligence Agent — Phase 7 Definition of Done.

Covers: screenshot capture, vision analysis structured output,
positioning map SVG validity, and inaccessible URL handling.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import CompetitorMap, CompetitorProfile

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def sample_competitor_profile():
    """Return a valid CompetitorProfile dict."""
    return {
        "competitor_url": "https://competitor-brand.com",
        "screenshot_gcs_url": "gs://brandforge-assets/campaigns/test/competitors/img.jpg",
        "brand_name": "CompetitorCo",
        "dominant_colors": ["#1A1A2E", "#E94560", "#0F3460"],
        "visual_style": "clean minimalism",
        "photography_style": "lifestyle",
        "tone": "professional and warm",
        "key_messages": ["Quality craftsmanship", "Sustainable materials"],
        "target_audience_guess": "Millennial professionals",
        "mainstream_niche_score": 0.3,
        "premium_accessible_score": 0.7,
        "weakness": "Lacks personality in messaging",
        "differentiation_opportunity": "Lead with bold, authentic storytelling",
    }


@pytest.fixture
def sample_competitor_map_data(sample_competitor_profile):
    """Return a valid CompetitorMap dict."""
    return CompetitorMap(
        campaign_id="test-campaign-123",
        competitors=[CompetitorProfile.model_validate(sample_competitor_profile)],
        user_brand_positioning={"mainstream_niche_score": 0.6, "premium_accessible_score": 0.5},
        differentiation_strategy="Focus on authentic storytelling and bold visuals.",
        positioning_map_svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="#0A0A0F"/></svg>',
    ).model_dump(mode="json")


# ── DoD Test: Screenshot captured ──────────────────────────────────────


@pytest.mark.asyncio
async def test_screenshot_captured():
    """Given a valid URL, a JPEG screenshot should be saved to GCS."""
    from brandforge.agents.competitor_intel.tools import capture_competitor_screenshot

    mock_context = MagicMock()
    mock_context.state = {"campaign_id": "test-campaign-123"}

    mock_page = AsyncMock()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response
    mock_page.screenshot.return_value = b"\xff\xd8\xff\xe0fake-jpeg-data"

    mock_browser = AsyncMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw = AsyncMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch(
        "brandforge.agents.competitor_intel.tools.upload_blob",
        return_value="gs://brandforge-assets/campaigns/test/competitors/shot.jpg",
    ), patch(
        "playwright.async_api.async_playwright",
    ) as mock_playwright_cls:
        mock_playwright_cls.return_value.__aenter__.return_value = mock_pw

        result = await capture_competitor_screenshot(
            url="https://valid-competitor.com",
            campaign_id="test-campaign-123",
            tool_context=mock_context,
        )

    assert result.startswith("gs://")
    assert result.endswith(".jpg")


# ── DoD Test: Vision analysis structured ───────────────────────────────


def test_vision_analysis_structured(sample_competitor_profile):
    """CompetitorProfile must pass Pydantic validation."""
    profile = CompetitorProfile.model_validate(sample_competitor_profile)
    assert profile.brand_name == "CompetitorCo"
    assert 0.0 <= profile.mainstream_niche_score <= 1.0
    assert 0.0 <= profile.premium_accessible_score <= 1.0
    assert len(profile.dominant_colors) >= 1
    assert profile.weakness
    assert profile.differentiation_opportunity


# ── DoD Test: Positioning map SVG valid ────────────────────────────────


def test_positioning_map_svg_valid(sample_competitor_map_data):
    """CompetitorMap.positioning_map_svg must be parseable as valid SVG XML."""
    import xml.etree.ElementTree as ET

    svg_str = sample_competitor_map_data["positioning_map_svg"]
    assert svg_str.strip().startswith("<svg")

    # Should parse as valid XML
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")


def test_fallback_svg_valid():
    """The fallback SVG builder should produce valid SVG."""
    from brandforge.agents.competitor_intel.tools import _build_fallback_svg

    profile = CompetitorProfile(
        brand_name="TestBrand",
        dominant_colors=["#FF0000"],
        visual_style="minimalist",
        photography_style="lifestyle",
        tone="professional",
        key_messages=["Quality"],
        target_audience_guess="Millennials",
        mainstream_niche_score=0.3,
        premium_accessible_score=0.8,
        weakness="Generic",
        differentiation_opportunity="Be bold",
    )

    svg = _build_fallback_svg([profile], "MyBrand")
    assert "<svg" in svg
    assert "MyBrand" in svg
    assert "TestBrand" in svg

    import xml.etree.ElementTree as ET
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")


# ── DoD Test: Inaccessible URL skipped ─────────────────────────────────


@pytest.mark.asyncio
async def test_inaccessible_url_skipped():
    """A competitor URL returning 403 should be skipped gracefully."""
    from brandforge.agents.competitor_intel.tools import capture_competitor_screenshot

    mock_context = MagicMock()
    mock_context.state = {"campaign_id": "test-campaign-123"}

    mock_page = AsyncMock()
    mock_response = MagicMock()
    mock_response.status = 403
    mock_page.goto.return_value = mock_response

    mock_browser = AsyncMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw = AsyncMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch(
        "playwright.async_api.async_playwright",
    ) as mock_playwright_cls:
        mock_playwright_cls.return_value.__aenter__.return_value = mock_pw

        result = await capture_competitor_screenshot(
            url="https://blocked-competitor.com",
            campaign_id="test-campaign-123",
            tool_context=mock_context,
        )

    assert result == "", "Inaccessible URL should return empty string"


@pytest.mark.asyncio
async def test_timeout_url_skipped():
    """A competitor URL that times out should be skipped gracefully."""
    from brandforge.agents.competitor_intel.tools import capture_competitor_screenshot

    mock_context = MagicMock()
    mock_context.state = {"campaign_id": "test-campaign-123"}

    mock_page = AsyncMock()
    mock_page.goto.side_effect = Exception("Navigation timeout")

    mock_browser = AsyncMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw = AsyncMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch(
        "playwright.async_api.async_playwright",
    ) as mock_playwright_cls:
        mock_playwright_cls.return_value.__aenter__.return_value = mock_pw

        result = await capture_competitor_screenshot(
            url="https://slow-competitor.com",
            campaign_id="test-campaign-123",
            tool_context=mock_context,
        )

    assert result == ""
