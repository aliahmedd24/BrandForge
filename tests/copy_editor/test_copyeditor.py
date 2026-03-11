"""Tests for the Copy Editor Agent — Definition of Done.

All tests use real Gemini API calls (no mocks).
"""

import uuid

import pytest

from brandforge.shared.models import BrandDNA, CopyPackage, PlatformCopy


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
@pytest.mark.timeout(120)
async def test_platform_copy_character_limits(mock_tool_context):
    """Platform-specific character limits are enforced."""
    from brandforge.agents.copy_editor.tools import review_and_refine_copy

    result = await review_and_refine_copy(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Copy generation failed: {result}"
    copy_data = mock_tool_context.state.get("copy_package_data")
    assert copy_data, "No copy package in state"

    package = CopyPackage.model_validate(copy_data)

    char_limits = {
        "instagram": 2200,
        "twitter_x": 280,
        "linkedin": 3000,
        "facebook": 2200,
    }

    for pc in package.platform_copies:
        limit = char_limits.get(pc.platform.value, 5000)
        assert len(pc.caption) <= limit, (
            f"{pc.platform.value} caption is {len(pc.caption)} chars (limit: {limit})"
        )


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(120)
async def test_hashtag_counts(mock_tool_context):
    """Instagram ≤ 30 hashtags, LinkedIn ≤ 5 hashtags."""
    from brandforge.agents.copy_editor.tools import review_and_refine_copy

    result = await review_and_refine_copy(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Copy generation failed: {result}"
    copy_data = mock_tool_context.state.get("copy_package_data")
    package = CopyPackage.model_validate(copy_data)

    for pc in package.platform_copies:
        if pc.platform.value == "instagram":
            assert len(pc.hashtags) <= 30, (
                f"Instagram has {len(pc.hashtags)} hashtags (max 30)"
            )
        elif pc.platform.value == "linkedin":
            assert len(pc.hashtags) <= 5, (
                f"LinkedIn has {len(pc.hashtags)} hashtags (max 5)"
            )


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(120)
async def test_brand_voice_score_threshold(mock_tool_context):
    """All PlatformCopy.brand_voice_score >= 0.7."""
    from brandforge.agents.copy_editor.tools import review_and_refine_copy

    result = await review_and_refine_copy(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Copy generation failed: {result}"
    copy_data = mock_tool_context.state.get("copy_package_data")
    package = CopyPackage.model_validate(copy_data)

    for pc in package.platform_copies:
        assert pc.brand_voice_score >= 0.7, (
            f"{pc.platform.value} brand_voice_score is {pc.brand_voice_score} (min 0.7)"
        )
