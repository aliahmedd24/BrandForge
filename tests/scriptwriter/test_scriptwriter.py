"""Tests for the Scriptwriter Agent — Definition of Done.

All tests use real Gemini API calls (no mocks).
"""

import json
import uuid

import pytest

from brandforge.shared.models import BrandDNA, VideoScript


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
async def test_generates_three_durations(mock_tool_context):
    """Scriptwriter produces 15s, 30s, and 60s scripts for a given platform."""
    from brandforge.agents.scriptwriter.tools import generate_video_scripts

    result = await generate_video_scripts(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        campaign_goal="product launch",
        platforms="instagram",
        tool_context=mock_tool_context,
    )

    assert "error" not in result, f"Script generation failed: {result}"
    scripts_data = mock_tool_context.state.get("video_scripts_data", [])
    durations = {s["duration_seconds"] for s in scripts_data}
    assert 15 in durations, "Missing 15s script"
    assert 30 in durations, "Missing 30s script"
    assert 60 in durations, "Missing 60s script"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(120)
async def test_script_schema_valid(mock_tool_context):
    """All VideoScript objects pass Pydantic validation."""
    from brandforge.agents.scriptwriter.tools import generate_video_scripts

    await generate_video_scripts(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        campaign_goal="product launch",
        platforms="instagram",
        tool_context=mock_tool_context,
    )

    scripts_data = mock_tool_context.state.get("video_scripts_data", [])
    assert len(scripts_data) > 0, "No scripts generated"

    for script_dict in scripts_data:
        script = VideoScript.model_validate(script_dict)
        assert script.hook, "Script missing hook"
        assert script.cta, "Script missing CTA"
        assert len(script.scenes) > 0, "Script has no scenes"
        assert script.campaign_id, "Script missing campaign_id"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(120)
async def test_forbidden_words_absent(mock_tool_context, sample_brand_dna):
    """No do_not_use words appear in any script text."""
    from brandforge.agents.scriptwriter.tools import generate_video_scripts

    await generate_video_scripts(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        campaign_goal="product launch",
        platforms="instagram",
        tool_context=mock_tool_context,
    )

    scripts_data = mock_tool_context.state.get("video_scripts_data", [])
    assert len(scripts_data) > 0, "No scripts generated"

    for script_dict in scripts_data:
        script = VideoScript.model_validate(script_dict)
        all_text = " ".join([
            script.hook,
            script.cta,
            *[s.voiceover for s in script.scenes],
            *[s.visual_description for s in script.scenes],
            *[s.text_overlay or "" for s in script.scenes],
        ]).lower()

        for forbidden in sample_brand_dna.do_not_use:
            word = forbidden.split("(")[0].strip().lower()
            if word:
                assert word not in all_text, (
                    f"Forbidden word '{word}' found in {script.platform.value} "
                    f"{script.duration_seconds}s script"
                )
