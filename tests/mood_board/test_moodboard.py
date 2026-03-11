"""Tests for the Mood Board Director Agent — Definition of Done.

All tests use real Imagen API + GCS calls (no mocks).
"""

import uuid

import pytest

from brandforge.shared.models import BrandDNA
from brandforge.shared.storage import download_blob


@pytest.fixture
def mock_tool_context(sample_brand_dna):
    """Create a minimal tool context-like object with state for testing."""

    class FakeToolContext:
        """Minimal ToolContext stub for direct tool function testing."""

        def __init__(self):
            """Initialize with empty state."""
            self.state = {}

    ctx = FakeToolContext()
    ctx.state["brand_dna"] = sample_brand_dna.model_dump(mode="json")
    return ctx


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(300)
async def test_generates_six_images(mock_tool_context):
    """Exactly 6 images are stored in GCS and URIs are returned."""
    from brandforge.agents.mood_board.tools import generate_mood_board_images

    result = await generate_mood_board_images(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        num_images=6,
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Mood board generation failed: {result}"
    gcs_urls = mock_tool_context.state.get("mood_board_urls", [])
    assert len(gcs_urls) == 6, f"Expected 6 images, got {len(gcs_urls)}"

    # Verify each URL is a valid GCS URI
    for url in gcs_urls:
        assert url.startswith("gs://"), f"Invalid GCS URI: {url}"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(600)
async def test_pdf_generated(mock_tool_context):
    """Mood board PDF is created and starts with PDF header."""
    from brandforge.agents.mood_board.tools import (
        assemble_mood_board_pdf,
        generate_mood_board_images,
    )

    campaign_id = f"test-{uuid.uuid4().hex[:8]}"

    # First generate the images
    await generate_mood_board_images(
        campaign_id=campaign_id,
        num_images=6,
        tool_context=mock_tool_context,
    )

    # Then assemble the PDF
    pdf_uri = await assemble_mood_board_pdf(
        campaign_id=campaign_id,
        tool_context=mock_tool_context,
    )

    assert pdf_uri.startswith("gs://"), f"Invalid PDF URI: {pdf_uri}"

    # Download and verify PDF header
    blob_path = pdf_uri.split("/", 3)[3] if pdf_uri.startswith("gs://") else pdf_uri
    pdf_bytes = download_blob(blob_path)
    assert pdf_bytes[:4] == b"%PDF", "PDF file does not start with %PDF header"
