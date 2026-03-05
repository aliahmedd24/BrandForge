"""Scriptwriter unit tests — Phase 2 Definition of Done.

All external APIs (Gemini, Firestore, GCS, Pub/Sub) are mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.scriptwriter.tools import (
    generate_video_scripts,
    store_scripts,
)
from brandforge.shared.models import VideoScript

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BRAND_DNA: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "version": 1,
    "brand_name": "Earthbrew",
    "brand_essence": "Coffee that gives back to the earth.",
    "brand_personality": ["warm", "authentic", "bold", "grounded", "sustainable"],
    "tone_of_voice": "Direct and quietly confident.",
    "color_palette": {
        "primary": "#2D3A2E",
        "secondary": "#C4894F",
        "accent": "#F4A261",
        "background": "#FAF3E0",
        "text": "#1A1A1A",
    },
    "typography": {
        "heading_font": "Canela Display",
        "body_font": "Neue Haas Grotesk",
        "font_personality": "Editorial, warm",
    },
    "primary_persona": {
        "name": "Urban Eco-Conscious Millennial",
        "age_range": "25-35",
        "values": ["sustainability"],
        "pain_points": ["greenwashing"],
        "content_habits": ["heavy Instagram user"],
    },
    "messaging_pillars": [
        {
            "title": "Radical Authenticity",
            "one_liner": "Real beans, real impact.",
            "supporting_points": ["Farm-to-cup traceability"],
            "avoid": ["greenwashing"],
        }
    ],
    "visual_direction": "Warm earth tones, close-up macro photography.",
    "platform_strategy": {
        "instagram": "Lifestyle shots",
        "tiktok": "Quick brew tutorials",
    },
    "do_not_use": ["premium", "luxury", "best coffee ever"],
    "source_brief_summary": "Brand: Earthbrew. Sustainable coffee.",
}


def _make_script_dict(platform: str, duration: int) -> dict:
    """Create a sample VideoScript dict for testing."""
    return {
        "id": str(uuid.uuid4()),
        "campaign_id": "camp-001",
        "platform": platform,
        "duration_seconds": duration,
        "aspect_ratio": "9:16" if platform in ("tiktok", "instagram") else "16:9",
        "hook": f"Stop scrolling — {platform} hook",
        "scenes": [
            {
                "scene_number": 1,
                "duration_seconds": duration,
                "visual_description": "Close-up of coffee beans being roasted.",
                "voiceover": "Every bean tells a story.",
                "text_overlay": None,
                "emotion": "warm",
            }
        ],
        "cta": "Tap to explore",
        "brand_dna_version": 1,
    }


def _make_genai_mock(response_text: str) -> MagicMock:
    """Create a mock genai.Client that returns the given text."""
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Test 1: Generates three durations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_three_durations() -> None:
    """Scriptwriter produces 15s, 30s, 60s scripts per platform."""
    # Generate mock responses for each platform × duration combo
    durations = [15, 30, 60]
    platforms = list(SAMPLE_BRAND_DNA["platform_strategy"].keys())

    all_scripts = []
    for platform in platforms:
        for dur in durations:
            all_scripts.append(_make_script_dict(platform, dur))

    # Mock: Firestore returns the BrandDNA, Gemini returns one script per call
    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    call_count = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_count
        idx = call_count % len(all_scripts)
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(all_scripts[idx])
        return mock_resp

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(side_effect=_side_effect)

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch(
            "brandforge.agents.scriptwriter.tools.genai.Client",
            return_value=mock_client,
        ),
    ):
        result = await generate_video_scripts(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"
    data = result["data"]

    # Check all 3 durations exist
    durations_found = {s["duration_seconds"] for s in data}
    assert 15 in durations_found
    assert 30 in durations_found
    assert 60 in durations_found


# ---------------------------------------------------------------------------
# Test 2: Script schema validates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_script_schema_valid() -> None:
    """All generated scripts pass Pydantic VideoScript validation."""
    script_dict = _make_script_dict("instagram", 30)
    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_client = _make_genai_mock(json.dumps(script_dict))

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch(
            "brandforge.agents.scriptwriter.tools.genai.Client",
            return_value=mock_client,
        ),
    ):
        result = await generate_video_scripts(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"
    for script_data in result["data"]:
        script = VideoScript(**script_data)
        assert script.campaign_id == "camp-001"
        assert len(script.scenes) >= 1
        assert script.hook
        assert script.cta


# ---------------------------------------------------------------------------
# Test 3: Forbidden words absent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forbidden_words_absent() -> None:
    """No do_not_use words appear in any script text."""
    clean_script = _make_script_dict("instagram", 15)

    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_client = _make_genai_mock(json.dumps(clean_script))

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch(
            "brandforge.agents.scriptwriter.tools.genai.Client",
            return_value=mock_client,
        ),
    ):
        result = await generate_video_scripts(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"
    for script_data in result["data"]:
        all_text = " ".join([
            script_data["hook"],
            script_data["cta"],
            *[s["voiceover"] for s in script_data["scenes"]],
            *[s["visual_description"] for s in script_data["scenes"]],
        ]).lower()

        for forbidden in SAMPLE_BRAND_DNA["do_not_use"]:
            assert forbidden.lower() not in all_text, (
                f"Forbidden word '{forbidden}' found in script text"
            )
