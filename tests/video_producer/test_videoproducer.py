"""Video Producer unit tests — Phase 2 Definition of Done.

All external APIs (Veo, TTS, FFmpeg, Firestore, GCS, Pub/Sub) are mocked.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.video_producer.tools import (
    compose_final_video,
    poll_veo_operation,
    wait_for_scriptwriter,
)
from brandforge.shared.models import AgentStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCRIPT: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "platform": "instagram",
    "duration_seconds": 15,
    "aspect_ratio": "9:16",
    "hook": "Stop scrolling",
    "scenes": [
        {
            "scene_number": 1,
            "duration_seconds": 15,
            "visual_description": "Coffee beans close-up.",
            "voiceover": "Every bean tells a story.",
            "text_overlay": None,
            "emotion": "warm",
        }
    ],
    "cta": "Tap to explore",
    "brand_dna_version": 1,
}


# ---------------------------------------------------------------------------
# Test 1: Waits for scriptwriter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_waits_for_scriptwriter() -> None:
    """wait_for_scriptwriter blocks until scriptwriter AgentRun status == complete."""
    completed_run = {
        "agent_name": "scriptwriter",
        "status": AgentStatus.COMPLETE,
        "campaign_id": "camp-001",
    }
    mock_query = AsyncMock(return_value=[completed_run, SAMPLE_SCRIPT])

    with patch("brandforge.shared.firestore.query_collection", mock_query):
        result = await wait_for_scriptwriter(
            campaign_id="camp-001",
            timeout_seconds=10,
        )

    assert result["status"] == "success"
    assert "script_ids" in result


# ---------------------------------------------------------------------------
# Test 2: Veo poll timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_veo_poll_timeout() -> None:
    """10-min timeout → failed status + error message."""
    # Mock an operation that never completes
    mock_op = MagicMock()
    mock_op.done = False

    mock_client = MagicMock()
    mock_client.get_operation = MagicMock(return_value=mock_op)

    with patch(
        "brandforge.agents.video_producer.tools.aiplatform.gapic.PredictionServiceClient",
        return_value=mock_client,
    ):
        result = await poll_veo_operation(
            operation_id="op-test-123",
            timeout_seconds=1,  # Very short timeout for testing
        )

    assert result["status"] == "error"
    assert "timed out" in result["error"].lower()


# ---------------------------------------------------------------------------
# Test 3: Final video has audio (composition succeeds)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_final_video_has_audio() -> None:
    """compose_final_video merges video + audio and returns final URL."""
    mock_merge = AsyncMock(return_value="gs://bucket/campaigns/camp-001/videos/final.mp4")
    mock_query = AsyncMock(return_value=[{"id": "vid-001", "script_id": "script-001"}])
    mock_update = AsyncMock()
    mock_create = AsyncMock(return_value="run-001")
    mock_publish = AsyncMock(return_value="msg-001")

    with (
        patch("brandforge.shared.video_utils.merge_video_audio", mock_merge),
        patch("brandforge.shared.firestore.query_collection", mock_query),
        patch("brandforge.shared.firestore.update_document", mock_update),
        patch("brandforge.shared.firestore.create_document", mock_create),
        patch("brandforge.shared.pubsub.publish_message", mock_publish),
    ):
        result = await compose_final_video(
            raw_video_gcs="gs://bucket/raw.mp4",
            audio_gcs="gs://bucket/audio.mp3",
            campaign_id="camp-001",
            script_id="script-001",
        )

    assert result["status"] == "success"
    assert "final_video_gcs" in result
    assert result["final_video_gcs"].endswith(".mp4")
    mock_merge.assert_called_once()
    mock_publish.assert_called_once()
