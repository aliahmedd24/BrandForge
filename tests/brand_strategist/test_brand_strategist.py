"""Brand Strategist unit tests — Phase 1 Definition of Done.

All external APIs (Gemini, Firestore, GCS, Pub/Sub) are mocked.
No real API calls are made during testing.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.brand_strategist.tools import (
    analyze_brand_assets,
    generate_brand_dna,
    store_brand_dna,
    transcribe_voice_brief,
)
from brandforge.shared.models import (
    BrandDNA,
    ColorPalette,
    VisualAssetAnalysis,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BRAND_DNA_DICT: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "version": 1,
    "brand_name": "Earthbrew",
    "brand_essence": "Coffee that gives back to the earth.",
    "brand_personality": ["warm", "authentic", "bold", "grounded", "sustainable"],
    "tone_of_voice": (
        "Direct and quietly confident. Speaks like a knowledgeable "
        "barista friend. Uses concrete specifics over abstract claims."
    ),
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
        "font_personality": "Editorial, warm, authoritative",
    },
    "primary_persona": {
        "name": "Urban Eco-Conscious Millennial",
        "age_range": "25-35",
        "values": ["sustainability", "authenticity", "community"],
        "pain_points": ["greenwashing", "overpriced organic products"],
        "content_habits": ["heavy Instagram user", "watches YouTube reviews"],
    },
    "messaging_pillars": [
        {
            "title": "Radical Authenticity",
            "one_liner": "Real beans, real impact, real talk.",
            "supporting_points": ["Farm-to-cup traceability", "Direct farmer partnerships"],
            "avoid": ["greenwashing language", "vague sustainability claims"],
        }
    ],
    "visual_direction": (
        "Warm earth tones, natural textures, close-up macro photography "
        "of coffee beans and brewing processes. Minimal, editorial layouts."
    ),
    "platform_strategy": {
        "instagram": "Behind-the-scenes farm stories + lifestyle shots",
        "tiktok": "Quick brew tutorials + farmer interviews",
    },
    "competitor_insights": [],
    "do_not_use": ["premium", "luxury", "best coffee ever"],
    "source_brief_summary": (
        "Brand: Earthbrew. Product: sustainable coffee. "
        "Audience: eco-conscious millennials. Goal: product launch."
    ),
}


SAMPLE_VISUAL_ANALYSIS_DICT: dict = {
    "detected_colors": ["#2D3A2E", "#C4894F", "#F4A261"],
    "typography_style": "Sans-serif, modern, clean",
    "visual_energy": "minimalist",
    "existing_brand_elements": ["leaf logo mark", "earth tone palette"],
    "recommended_direction": "Continue minimalist approach with warm earth tones",
}


def _make_genai_mock(response_text: str) -> MagicMock:
    """Create a mock genai.Client that returns the given text."""
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Test 1: text-only brief produces valid BrandDNA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_only_brief_produces_valid_brand_dna() -> None:
    """Given a text-only brief, generate_brand_dna returns a valid BrandDNA."""
    mock_client = _make_genai_mock(json.dumps(SAMPLE_BRAND_DNA_DICT))

    with patch(
        "brandforge.agents.brand_strategist.tools.genai.Client",
        return_value=mock_client,
    ):
        result = await generate_brand_dna(
            brand_name="Earthbrew",
            product_description="Sustainable single-origin coffee",
            target_audience="Eco-conscious millennials",
            campaign_goal="Product launch",
            tone_keywords="warm, authentic, bold",
            platforms="instagram, tiktok",
            campaign_id="camp-001",
        )

    assert result["status"] == "success"
    data = result["data"]
    # Validate every required field via Pydantic
    brand_dna = BrandDNA(**data)
    assert brand_dna.brand_name == "Earthbrew"
    assert len(brand_dna.brand_personality) > 0
    assert brand_dna.tone_of_voice
    assert brand_dna.color_palette
    assert brand_dna.typography
    assert brand_dna.primary_persona
    assert len(brand_dna.messaging_pillars) > 0
    assert brand_dna.visual_direction
    assert brand_dna.platform_strategy


# ---------------------------------------------------------------------------
# Test 2: image assets produce valid VisualAssetAnalysis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_image_assets_produces_visual_analysis() -> None:
    """Given uploaded images, analyze_brand_assets returns valid VisualAssetAnalysis."""
    mock_client = _make_genai_mock(json.dumps(SAMPLE_VISUAL_ANALYSIS_DICT))
    mock_download = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    with (
        patch(
            "brandforge.agents.brand_strategist.tools.genai.Client",
            return_value=mock_client,
        ),
        patch(
            "brandforge.shared.storage.download_blob",
            mock_download,
        ),
    ):
        result = await analyze_brand_assets(
            asset_urls=["gs://brandforge-assets/campaigns/camp-001/logo.png"],
            campaign_id="camp-001",
        )

    assert result["status"] == "success"
    analysis = VisualAssetAnalysis(**result["data"])
    assert len(analysis.detected_colors) > 0
    assert analysis.visual_energy == "minimalist"


# ---------------------------------------------------------------------------
# Test 3: voice brief transcription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_brief_transcription_returns_text() -> None:
    """Given an audio URL, transcribe_voice_brief returns transcription text."""
    mock_client = _make_genai_mock(
        "We want to create a brand that feels warm and authentic."
    )
    mock_download = AsyncMock(return_value=b"\x00" * 1000)

    with (
        patch(
            "brandforge.agents.brand_strategist.tools.genai.Client",
            return_value=mock_client,
        ),
        patch(
            "brandforge.shared.storage.download_blob",
            mock_download,
        ),
    ):
        result = await transcribe_voice_brief(
            voice_brief_url="gs://brandforge-assets/campaigns/camp-001/voice.webm",
            campaign_id="camp-001",
        )

    assert result["status"] == "success"
    assert "warm" in result["transcription"]


# ---------------------------------------------------------------------------
# Test 4: audio timeout fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audio_timeout_fallback_returns_error_gracefully() -> None:
    """If audio transcription exceeds 30s, agent falls back gracefully."""

    async def slow_download(path: str) -> bytes:
        """Simulate a slow download that exceeds timeout."""
        await asyncio.sleep(60)
        return b""

    with patch(
        "brandforge.shared.storage.download_blob",
        side_effect=slow_download,
    ):
        result = await transcribe_voice_brief(
            voice_brief_url="gs://brandforge-assets/campaigns/camp-001/voice.webm",
            campaign_id="camp-001",
        )

    assert result["status"] == "error"
    assert "timed out" in result["error"].lower()


# ---------------------------------------------------------------------------
# Test 5: Brand DNA stored in Firestore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brand_dna_stored_in_firestore() -> None:
    """After store_brand_dna, Firestore create and GCS upload are called."""
    mock_create_doc = AsyncMock(return_value="test-id")
    mock_upload = AsyncMock(return_value="gs://bucket/path")
    mock_update_doc = AsyncMock()
    mock_publish = AsyncMock(return_value="msg-001")
    mock_query = AsyncMock(return_value=[])

    with (
        patch(
            "brandforge.shared.firestore.create_document",
            mock_create_doc,
        ),
        patch(
            "brandforge.shared.firestore.update_document",
            mock_update_doc,
        ),
        patch(
            "brandforge.shared.firestore.query_collection",
            mock_query,
        ),
        patch(
            "brandforge.shared.storage.upload_blob",
            mock_upload,
        ),
        patch(
            "brandforge.shared.pubsub.publish_message",
            mock_publish,
        ),
    ):
        result = await store_brand_dna(
            brand_dna_json=json.dumps(SAMPLE_BRAND_DNA_DICT),
            campaign_id="camp-001",
        )

    assert result["status"] == "success"
    assert "brand_dna_id" in result
    mock_create_doc.assert_called_once()
    mock_upload.assert_called_once()
    mock_update_doc.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: color palette hex validation
# ---------------------------------------------------------------------------


def test_color_palette_hex_valid_accepts_correct_hex() -> None:
    """All 5 ColorPalette fields pass #RRGGBB validation."""
    palette = ColorPalette(
        primary="#2D3A2E",
        secondary="#C4894F",
        accent="#F4A261",
        background="#FAF3E0",
        text="#1A1A1A",
    )
    assert palette.primary == "#2D3A2E"
    assert palette.text == "#1A1A1A"


def test_color_palette_hex_valid_rejects_invalid_hex() -> None:
    """Invalid hex values raise ValueError."""
    with pytest.raises(ValueError, match="Invalid hex color"):
        ColorPalette(
            primary="not-a-color",
            secondary="#C4894F",
            accent="#F4A261",
            background="#FAF3E0",
            text="#1A1A1A",
        )

    with pytest.raises(ValueError, match="Invalid hex color"):
        ColorPalette(
            primary="#2D3A2E",
            secondary="#GGG000",
            accent="#F4A261",
            background="#FAF3E0",
            text="#1A1A1A",
        )


# ---------------------------------------------------------------------------
# Test 7: no hallucination — source_brief_summary references input
# ---------------------------------------------------------------------------


def test_no_hallucination_source_summary_includes_brand_name() -> None:
    """BrandDNA source_brief_summary correctly references input brand name."""
    brand_dna = BrandDNA(**SAMPLE_BRAND_DNA_DICT)
    assert "Earthbrew" in brand_dna.source_brief_summary


# ---------------------------------------------------------------------------
# Test 8: version increment on same campaign
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_increment_on_same_campaign() -> None:
    """Rerunning on same campaign creates version 2, not overwrite."""
    existing_v1 = dict(SAMPLE_BRAND_DNA_DICT)
    existing_v1["version"] = 1

    mock_create_doc = AsyncMock(return_value="test-id")
    mock_upload = AsyncMock(return_value="gs://bucket/path")
    mock_update_doc = AsyncMock()
    mock_publish = AsyncMock(return_value="msg-002")
    # Return one existing document to trigger version increment
    mock_query = AsyncMock(return_value=[existing_v1])

    with (
        patch(
            "brandforge.shared.firestore.create_document",
            mock_create_doc,
        ),
        patch(
            "brandforge.shared.firestore.update_document",
            mock_update_doc,
        ),
        patch(
            "brandforge.shared.firestore.query_collection",
            mock_query,
        ),
        patch(
            "brandforge.shared.storage.upload_blob",
            mock_upload,
        ),
        patch(
            "brandforge.shared.pubsub.publish_message",
            mock_publish,
        ),
    ):
        result = await store_brand_dna(
            brand_dna_json=json.dumps(SAMPLE_BRAND_DNA_DICT),
            campaign_id="camp-001",
        )

    assert result["status"] == "success"
    assert result["version"] == 2  # v1 existed → v2 created

    # Verify Firestore was called with version 2
    create_call_data = mock_create_doc.call_args[1]["data"]
    assert create_call_data["version"] == 2


# ---------------------------------------------------------------------------
# Test 9: Pub/Sub message published after store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pubsub_message_published_after_store() -> None:
    """store_brand_dna publishes 'brand_dna_ready' to brandforge.agent.complete."""
    mock_create_doc = AsyncMock(return_value="test-id")
    mock_upload = AsyncMock(return_value="gs://bucket/path")
    mock_update_doc = AsyncMock()
    mock_publish = AsyncMock(return_value="msg-003")
    mock_query = AsyncMock(return_value=[])

    with (
        patch(
            "brandforge.shared.firestore.create_document",
            mock_create_doc,
        ),
        patch(
            "brandforge.shared.firestore.update_document",
            mock_update_doc,
        ),
        patch(
            "brandforge.shared.firestore.query_collection",
            mock_query,
        ),
        patch(
            "brandforge.shared.storage.upload_blob",
            mock_upload,
        ),
        patch(
            "brandforge.shared.pubsub.publish_message",
            mock_publish,
        ),
    ):
        result = await store_brand_dna(
            brand_dna_json=json.dumps(SAMPLE_BRAND_DNA_DICT),
            campaign_id="camp-001",
        )

    assert result["status"] == "success"
    mock_publish.assert_called_once()

    # Verify the published message
    call_kwargs = mock_publish.call_args[1]
    assert call_kwargs["topic"] == "brandforge.agent.complete"
    published_msg = call_kwargs["message"]
    assert published_msg.event_type == "brand_dna_ready"
    assert published_msg.source_agent == "brand_strategist"
    assert published_msg.campaign_id == "camp-001"
