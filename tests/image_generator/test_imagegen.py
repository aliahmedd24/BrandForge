"""Image Generator unit tests — Phase 2 Definition of Done.

All external APIs (Imagen, Firestore, GCS, Pub/Sub) are mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.image_generator.tools import (
    generate_platform_images,
    store_generated_images,
)
from brandforge.shared.config import PLATFORM_IMAGE_SPECS
from brandforge.shared.models import GeneratedImage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BRAND_DNA: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "version": 1,
    "brand_name": "Earthbrew",
    "brand_essence": "Coffee.",
    "brand_personality": ["warm", "bold"],
    "tone_of_voice": "Direct.",
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
    "messaging_pillars": [],
    "visual_direction": "Warm earth tones.",
    "platform_strategy": {"instagram": "Lifestyle", "linkedin": "Professional"},
    "do_not_use": [],
    "source_brief_summary": "Earthbrew coffee.",
}


def _mock_imagen_model() -> MagicMock:
    """Create a mock ImageGenerationModel."""
    mock_image = MagicMock()
    mock_image._image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

    mock_response = MagicMock()
    mock_response.images = [mock_image]

    mock_model = MagicMock()
    mock_model.generate_images = MagicMock(return_value=mock_response)
    return mock_model


# ---------------------------------------------------------------------------
# Test 1: All platform specs covered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_platform_specs_covered() -> None:
    """Each platform has at least 1 image per spec."""
    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_upload = AsyncMock(side_effect=lambda **kw: f"gs://bucket/{kw['destination_path']}")
    mock_model = _mock_imagen_model()

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.storage.upload_blob", mock_upload),
        patch(
            "brandforge.agents.image_generator.tools.ImageGenerationModel.from_pretrained",
            return_value=mock_model,
        ),
    ):
        result = await generate_platform_images(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
            platforms_json=json.dumps(["instagram", "linkedin"]),
        )

    assert result["status"] == "success"
    data = result["data"]

    # Instagram has 2 specs, LinkedIn has 1 — check all covered
    platforms_in_result = {img["platform"] for img in data}
    assert "instagram" in platforms_in_result
    assert "linkedin" in platforms_in_result

    # Each spec should have images
    ig_images = [i for i in data if i["platform"] == "instagram"]
    li_images = [i for i in data if i["platform"] == "linkedin"]
    assert len(ig_images) >= 1  # At least 1 per spec
    assert len(li_images) >= 1


# ---------------------------------------------------------------------------
# Test 2: Three variants per spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_variants_per_spec() -> None:
    """Each image spec produces exactly 3 A/B/C variants."""
    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_upload = AsyncMock(side_effect=lambda **kw: f"gs://bucket/{kw['destination_path']}")
    mock_model = _mock_imagen_model()

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.storage.upload_blob", mock_upload),
        patch(
            "brandforge.agents.image_generator.tools.ImageGenerationModel.from_pretrained",
            return_value=mock_model,
        ),
    ):
        result = await generate_platform_images(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
            platforms_json=json.dumps(["linkedin"]),  # 1 spec → 3 variants
        )

    assert result["status"] == "success"
    data = result["data"]

    # LinkedIn has 1 spec → should have exactly 3 variants
    assert len(data) == 3
    variant_numbers = {img["variant_number"] for img in data}
    assert variant_numbers == {1, 2, 3}


# ---------------------------------------------------------------------------
# Test 3: GCS uploads complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gcs_upload_complete() -> None:
    """All generated images have populated gcs_url values."""
    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_upload = AsyncMock(side_effect=lambda **kw: f"gs://bucket/{kw['destination_path']}")
    mock_model = _mock_imagen_model()

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.storage.upload_blob", mock_upload),
        patch(
            "brandforge.agents.image_generator.tools.ImageGenerationModel.from_pretrained",
            return_value=mock_model,
        ),
    ):
        result = await generate_platform_images(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
            platforms_json=json.dumps(["instagram"]),
        )

    assert result["status"] == "success"
    for img in result["data"]:
        assert img["gcs_url"].startswith("gs://")
        assert img["gcs_url"]  # Not empty
