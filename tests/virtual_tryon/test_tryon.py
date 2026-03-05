"""Virtual Try-On unit tests — Phase 2 Definition of Done.

All external APIs (Virtual Try-On, Firestore, GCS, Pub/Sub) are mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.virtual_tryon.tools import generate_tryon_images

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_FASHION_BRAND_DNA: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "version": 1,
    "brand_name": "UrbanThread",
    "brand_essence": "Modern streetwear clothing for the conscious generation.",
    "brand_personality": ["bold", "urban", "sustainable"],
    "tone_of_voice": "Street-smart and authentic.",
    "color_palette": {
        "primary": "#1A1A1A",
        "secondary": "#F5F5F5",
        "accent": "#FF4444",
        "background": "#FFFFFF",
        "text": "#333333",
    },
    "typography": {
        "heading_font": "Futura Bold",
        "body_font": "Helvetica",
        "font_personality": "Clean, modern",
    },
    "primary_persona": {
        "name": "Gen-Z Trendsetter",
        "age_range": "18-25",
        "values": ["style"],
        "pain_points": ["fast fashion"],
        "content_habits": ["TikTok"],
    },
    "messaging_pillars": [],
    "visual_direction": "High contrast, urban settings.",
    "platform_strategy": {"instagram": "Lookbooks"},
    "do_not_use": [],
    "source_brief_summary": "UrbanThread streetwear clothing.",
}


def _mock_tryon_response() -> MagicMock:
    """Create a mock Vertex AI prediction response for virtual try-on."""
    import base64

    mock_prediction = MagicMock()
    mock_prediction.get = MagicMock(
        return_value=base64.b64encode(b"\x89PNG" + b"\x00" * 100).decode("utf-8")
    )

    mock_response = MagicMock()
    mock_response.predictions = [mock_prediction]

    mock_client = MagicMock()
    mock_client.predict = MagicMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Test 1: Generates variants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_variants() -> None:
    """3 variants returned per product × model combination."""
    mock_get_doc = AsyncMock(return_value=SAMPLE_FASHION_BRAND_DNA)
    mock_download = AsyncMock(return_value=b"\x89PNG" + b"\x00" * 200)
    mock_upload = AsyncMock(side_effect=lambda **kw: f"gs://bucket/{kw['destination_path']}")
    mock_tryon_client = _mock_tryon_response()

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.storage.download_blob", mock_download),
        patch("brandforge.shared.storage.upload_blob", mock_upload),
        patch(
            "brandforge.agents.virtual_tryon.tools.aiplatform.gapic.PredictionServiceClient",
            return_value=mock_tryon_client,
        ),
    ):
        result = await generate_tryon_images(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_FASHION_BRAND_DNA["id"],
            product_image_gcs="gs://bucket/product.png",
            model_image_gcs="gs://bucket/model.png",
            num_variants=3,
        )

    assert result["status"] == "success"
    assert result["variant_count"] == 3
    assert len(result["data"]) == 3

    variant_numbers = {v["variant_number"] for v in result["data"]}
    assert variant_numbers == {1, 2, 3}


# ---------------------------------------------------------------------------
# Test 2: GCS uploads complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gcs_upload_complete() -> None:
    """All generated try-on images have populated GCS URLs."""
    mock_get_doc = AsyncMock(return_value=SAMPLE_FASHION_BRAND_DNA)
    mock_download = AsyncMock(return_value=b"\x89PNG" + b"\x00" * 200)
    mock_upload = AsyncMock(side_effect=lambda **kw: f"gs://bucket/{kw['destination_path']}")
    mock_tryon_client = _mock_tryon_response()

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.storage.download_blob", mock_download),
        patch("brandforge.shared.storage.upload_blob", mock_upload),
        patch(
            "brandforge.agents.virtual_tryon.tools.aiplatform.gapic.PredictionServiceClient",
            return_value=mock_tryon_client,
        ),
    ):
        result = await generate_tryon_images(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_FASHION_BRAND_DNA["id"],
            product_image_gcs="gs://bucket/product.png",
            model_image_gcs="gs://bucket/model.png",
        )

    assert result["status"] == "success"
    for tryon in result["data"]:
        assert tryon["gcs_url"].startswith("gs://")
        assert tryon["gcs_url"]  # Not empty
