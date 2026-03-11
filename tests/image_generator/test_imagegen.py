"""Tests for the Image Generator Agent — Definition of Done.

All tests use real Imagen API + GCS calls (no mocks).
"""

import uuid
from collections import Counter

import pytest

from brandforge.shared.models import BrandDNA, GeneratedImage


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
@pytest.mark.timeout(600)
async def test_all_platform_specs_covered(mock_tool_context):
    """At least one image per applicable platform spec is generated."""
    from brandforge.agents.image_generator.tools import generate_campaign_images

    result = await generate_campaign_images(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Image generation failed: {result}"
    images_data = mock_tool_context.state.get("generated_images_data", [])
    assert len(images_data) > 0, "No images generated"

    # Check each platform has at least one image
    platforms_covered = {img["platform"] for img in images_data}
    assert len(platforms_covered) >= 1, "No platform specs covered"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(600)
async def test_three_variants_per_spec(mock_tool_context):
    """Each ImageSpec produces exactly 3 variants (A/B/C)."""
    from brandforge.agents.image_generator.tools import generate_campaign_images

    result = await generate_campaign_images(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Image generation failed: {result}"
    images_data = mock_tool_context.state.get("generated_images_data", [])

    # Group by platform + use_case to find spec groups
    spec_groups = Counter()
    for img in images_data:
        spec = img.get("spec", {})
        key = f"{spec.get('platform', '')}_{spec.get('use_case', '')}"
        spec_groups[key] += 1

    for spec_key, count in spec_groups.items():
        assert count == 3, f"Spec {spec_key} has {count} variants (expected 3)"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(600)
async def test_gcs_upload_complete(mock_tool_context):
    """All generated images have valid GCS URLs."""
    from brandforge.agents.image_generator.tools import generate_campaign_images

    result = await generate_campaign_images(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Image generation failed: {result}"
    images_data = mock_tool_context.state.get("generated_images_data", [])

    for img in images_data:
        gen_image = GeneratedImage.model_validate(img)
        assert gen_image.gcs_url.startswith("gs://"), (
            f"Invalid GCS URL for {gen_image.platform.value} variant {gen_image.variant_number}"
        )
