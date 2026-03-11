"""Tests for the Video Producer Agent — Definition of Done.

Tests verify dependency checking, timeout handling, and final composition.
"""

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
@pytest.mark.timeout(60)
async def test_waits_for_scriptwriter(mock_tool_context):
    """Agent returns error when video_scripts_data is empty/missing."""
    from brandforge.agents.video_producer.tools import submit_veo_generation

    # Do NOT set video_scripts_data in state
    result = await submit_veo_generation(
        campaign_id=f"test-{uuid.uuid4().hex[:8]}",
        script_id="nonexistent",
        tool_context=mock_tool_context,
    )

    assert result["status"] == "failed", "Should fail without scripts"
    assert "error" in result, "Should return error message"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(120)
async def test_veo_poll_timeout(mock_tool_context):
    """Short timeout results in status='failed'."""
    from brandforge.agents.video_producer.tools import poll_veo_operation

    # Use a fake operation name — polling should timeout quickly
    result = await poll_veo_operation(
        operation_name="operations/fake-nonexistent-op-12345",
        timeout_seconds=5,  # Very short timeout
        tool_context=mock_tool_context,
    )

    assert result["status"] == "failed", "Should fail on timeout or invalid operation"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(900)
async def test_final_video_has_audio(mock_tool_context, sample_video_script):
    """Full e2e: submit Veo → poll → voiceover → compose, verify audio track.

    Note: This test requires real Veo + TTS + FFmpeg and may take several minutes.
    """
    import subprocess

    from brandforge.agents.video_producer.tools import (
        compose_final_video,
        generate_voiceover,
        poll_veo_operation,
        submit_veo_generation,
    )
    from brandforge.shared.storage import download_blob

    campaign_id = f"test-{uuid.uuid4().hex[:8]}"
    script_data = sample_video_script.model_dump(mode="json")
    mock_tool_context.state["video_scripts_data"] = [script_data]

    # Step 1: Submit Veo
    submit_result = await submit_veo_generation(
        campaign_id=campaign_id,
        script_id=sample_video_script.id,
        tool_context=mock_tool_context,
    )

    if submit_result.get("status") == "failed":
        pytest.skip(f"Veo submission failed: {submit_result.get('error')}")

    # Step 2: Poll
    poll_result = await poll_veo_operation(
        operation_name=submit_result["operation_name"],
        timeout_seconds=600,
        tool_context=mock_tool_context,
    )

    if poll_result["status"] == "failed":
        pytest.skip(f"Veo generation failed: {poll_result.get('error')}")

    # Step 3: Voiceover
    audio_uri = await generate_voiceover(
        script_id=sample_video_script.id,
        tool_context=mock_tool_context,
    )

    # Step 4: Compose
    final_uri = await compose_final_video(
        campaign_id=campaign_id,
        script_id=sample_video_script.id,
        video_uri=poll_result["video_uri"],
        audio_uri=audio_uri,
        tool_context=mock_tool_context,
    )

    assert final_uri.startswith("gs://"), f"Invalid final video URI: {final_uri}"

    # Verify audio track with ffprobe
    blob_path = final_uri.split("/", 3)[3]
    video_bytes = download_blob(blob_path)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_bytes)
        tmp_path = f.name

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", tmp_path],
        capture_output=True, text=True,
    )
    import json
    streams = json.loads(probe.stdout)
    audio_streams = [s for s in streams.get("streams", []) if s.get("codec_type") == "audio"]
    assert len(audio_streams) > 0, "Final video has no audio track"
