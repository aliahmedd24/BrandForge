"""Mood Board Director unit tests — Phase 2 Definition of Done.

All external APIs (Gemini, Firestore, GCS, Pub/Sub) are mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.mood_board_director.tools import (
    assemble_mood_board_pdf,
    generate_mood_board_images,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BRAND_DNA: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "version": 1,
    "brand_name": "Earthbrew",
    "brand_essence": "Coffee that gives back to the earth.",
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
    "messaging_pillars": [],
    "visual_direction": "Warm earth tones, close-up macro photography.",
    "platform_strategy": {"instagram": "Lifestyle shots"},
    "do_not_use": [],
    "source_brief_summary": "Earthbrew sustainable coffee.",
}


def _make_image_response_mock() -> MagicMock:
    """Create a mock Gemini response that contains inline image data."""
    mock_part = MagicMock()
    mock_part.inline_data = MagicMock()
    # Use raw bytes (not b64) — the tool checks isinstance
    mock_part.inline_data.data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part]

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]

    mock_client = MagicMock()
    mock_client.models.generate_content = MagicMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Test 1: Generates six images
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_six_images() -> None:
    """Mood board produces exactly 6 reference images."""
    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_upload = AsyncMock(side_effect=lambda **kw: f"gs://bucket/{kw['destination_path']}")
    mock_create_doc = AsyncMock(return_value="doc-id")
    mock_client = _make_image_response_mock()

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.firestore.create_document", mock_create_doc),
        patch("brandforge.shared.storage.upload_blob", mock_upload),
        patch(
            "brandforge.agents.mood_board_director.tools.genai.Client",
            return_value=mock_client,
        ),
    ):
        result = await generate_mood_board_images(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"
    assert result["image_count"] == 6
    assert len(result["data"]) == 6

    # All images should have GCS URLs
    for img in result["data"]:
        assert img["gcs_url"].startswith("gs://")


# ---------------------------------------------------------------------------
# Test 2: PDF generated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_generated() -> None:
    """assemble_mood_board_pdf creates and uploads a PDF."""
    image_urls = [
        {"gcs_url": f"gs://bucket/campaigns/camp-001/mood_board/img_{i}.png", "category": "lifestyle"}
        for i in range(6)
    ]

    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_download = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    mock_upload = AsyncMock(return_value="gs://bucket/campaigns/camp-001/mood_board/mood_board.pdf")
    mock_create_doc = AsyncMock(return_value="doc-id")
    mock_publish = AsyncMock(return_value="msg-001")

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.firestore.create_document", mock_create_doc),
        patch("brandforge.shared.storage.download_blob", mock_download),
        patch("brandforge.shared.storage.upload_blob", mock_upload),
        patch("brandforge.shared.pubsub.publish_message", mock_publish),
    ):
        result = await assemble_mood_board_pdf(
            image_urls_json=json.dumps(image_urls),
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
            campaign_id="camp-001",
        )

    assert result["status"] == "success"
    assert "pdf_gcs_url" in result
    assert result["pdf_gcs_url"].endswith(".pdf")
    mock_upload.assert_called()
    mock_publish.assert_called_once()
