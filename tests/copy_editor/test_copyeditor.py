"""Copy Editor unit tests — Phase 2 Definition of Done.

All external APIs (Gemini, Firestore, GCS, Pub/Sub) are mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.copy_editor.tools import review_and_refine_copy
from brandforge.shared.models import CopyPackage, PlatformCopy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BRAND_DNA: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "version": 1,
    "brand_name": "Earthbrew",
    "brand_essence": "Coffee that gives back.",
    "brand_personality": ["warm", "authentic", "bold"],
    "tone_of_voice": "Direct and quietly confident.",
    "color_palette": {
        "primary": "#2D3A2E",
        "secondary": "#C4894F",
        "accent": "#F4A261",
        "background": "#FAF3E0",
        "text": "#1A1A1A",
    },
    "typography": {
        "heading_font": "Canela",
        "body_font": "Grotesk",
        "font_personality": "Editorial",
    },
    "primary_persona": {
        "name": "Millennial",
        "age_range": "25-35",
        "values": ["eco"],
        "pain_points": ["price"],
        "content_habits": ["IG"],
    },
    "messaging_pillars": [
        {
            "title": "Authenticity",
            "one_liner": "Real beans.",
            "supporting_points": ["Traceability"],
            "avoid": ["hype"],
        }
    ],
    "visual_direction": "Warm earth tones.",
    "platform_strategy": {
        "instagram": "Lifestyle shots",
        "twitter_x": "Punchy updates",
        "linkedin": "Professional thought leadership",
    },
    "do_not_use": ["premium", "luxury"],
    "source_brief_summary": "Earthbrew coffee.",
}


def _make_copy_response(platform: str) -> dict:
    """Create a valid PlatformCopy dict for a platform."""
    limits = {"instagram": 2200, "twitter_x": 280, "linkedin": 3000}
    max_len = limits.get(platform, 2200)

    caption = f"Discover the warmth of Earthbrew — every sip matters. #{platform}"
    if len(caption) > max_len:
        caption = caption[:max_len]

    hashtag_limit = 5 if platform == "linkedin" else 10
    hashtags = [f"#earthbrew{i}" for i in range(min(3, hashtag_limit))]

    return {
        "caption": caption,
        "headline": "Earthbrew: Real Beans, Real Impact",
        "hashtags": hashtags,
        "cta_text": "Explore now",
        "brand_voice_score": 0.85,
    }


def _make_genai_mock_for_platform(platform: str) -> MagicMock:
    """Create a mock genai.Client returning valid copy for a platform."""
    copy_data = _make_copy_response(platform)
    mock_response = MagicMock()
    mock_response.text = json.dumps(copy_data)
    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Test 1: Platform copy character limits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_copy_character_limits() -> None:
    """IG ≤2200, Twitter ≤280, LI ≤3000 character limits enforced."""
    platforms = list(SAMPLE_BRAND_DNA["platform_strategy"].keys())
    call_idx = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_idx
        platform = platforms[call_idx % len(platforms)]
        call_idx += 1
        resp = MagicMock()
        resp.text = json.dumps(_make_copy_response(platform))
        return resp

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(side_effect=_side_effect)

    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_query = AsyncMock(return_value=[])

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.firestore.query_collection", mock_query),
        patch(
            "brandforge.agents.copy_editor.tools.genai.Client",
            return_value=mock_client,
        ),
    ):
        result = await review_and_refine_copy(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"
    data = result["data"]
    package = CopyPackage(**data)

    limits = {"instagram": 2200, "twitter_x": 280, "linkedin": 3000}
    for pc in package.platform_copies:
        max_len = limits.get(pc.platform, 5000)
        assert len(pc.caption) <= max_len, (
            f"{pc.platform} caption exceeds {max_len} chars: {len(pc.caption)}"
        )


# ---------------------------------------------------------------------------
# Test 2: Hashtag counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hashtag_counts() -> None:
    """IG ≤30, LI ≤5 hashtag limits enforced."""
    platforms = list(SAMPLE_BRAND_DNA["platform_strategy"].keys())
    call_idx = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_idx
        platform = platforms[call_idx % len(platforms)]
        call_idx += 1
        resp = MagicMock()
        resp.text = json.dumps(_make_copy_response(platform))
        return resp

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(side_effect=_side_effect)

    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_query = AsyncMock(return_value=[])

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.firestore.query_collection", mock_query),
        patch(
            "brandforge.agents.copy_editor.tools.genai.Client",
            return_value=mock_client,
        ),
    ):
        result = await review_and_refine_copy(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"
    data = result["data"]
    package = CopyPackage(**data)

    for pc in package.platform_copies:
        if pc.platform == "instagram":
            assert len(pc.hashtags) <= 30
        if pc.platform == "linkedin":
            assert len(pc.hashtags) <= 5


# ---------------------------------------------------------------------------
# Test 3: Brand voice score threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brand_voice_score_threshold() -> None:
    """All brand voice scores must be ≥0.7."""
    platforms = list(SAMPLE_BRAND_DNA["platform_strategy"].keys())
    call_idx = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_idx
        platform = platforms[call_idx % len(platforms)]
        call_idx += 1
        resp = MagicMock()
        resp.text = json.dumps(_make_copy_response(platform))
        return resp

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(side_effect=_side_effect)

    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_query = AsyncMock(return_value=[])

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.firestore.query_collection", mock_query),
        patch(
            "brandforge.agents.copy_editor.tools.genai.Client",
            return_value=mock_client,
        ),
    ):
        result = await review_and_refine_copy(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"
    data = result["data"]
    package = CopyPackage(**data)

    for pc in package.platform_copies:
        assert pc.brand_voice_score >= 0.7, (
            f"{pc.platform} brand voice score too low: {pc.brand_voice_score}"
        )
