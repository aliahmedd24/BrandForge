"""Tests for the Sage Voice Orchestrator — Phase 7 Definition of Done.

Covers: narration audio generated, narration caching, voice feedback
classified, modification routed to agent, and barge-in handling.
"""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import VoiceFeedbackResult

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_tts_response():
    """Return mock TTS audio bytes."""
    return b"\x00\x00\x00\x1cftypisom\x00\x00fake-mp3-audio-data"


@pytest.fixture
def mock_tool_context():
    """Return a mock ToolContext with campaign state."""
    ctx = MagicMock()
    ctx.state = {
        "campaign_id": "test-campaign-123",
        "brand_dna": {
            "brand_essence": "A warm editorial brand",
            "tone_of_voice": "authentic and bold",
        },
        "trend_signals": [{"title": "trend1"}, {"title": "trend2"}],
        "generated_images": [{"id": "img1"}, {"id": "img2"}, {"id": "img3"}],
        "generated_videos": [{"id": "vid1"}],
        "qa_summary": {
            "brand_coherence_score": 0.89,
            "total_assets": 4,
            "failed_count": 1,
        },
        "platforms": ["instagram", "tiktok"],
    }
    return ctx


# ── DoD Test: Narration audio generated ────────────────────────────────


@pytest.mark.asyncio
async def test_narration_audio_generated(mock_tool_context, mock_tts_response):
    """narrate_agent_milestone must return a valid GCS URL pointing to audio."""
    from brandforge.agents.sage.tools import narrate_agent_milestone

    with patch(
        "brandforge.agents.sage.tools._synthesize_speech",
        new_callable=AsyncMock,
        return_value=mock_tts_response,
    ), patch(
        "brandforge.agents.sage.tools.download_blob",
        side_effect=Exception("Not found"),
    ), patch(
        "brandforge.agents.sage.tools.upload_blob",
        return_value="gs://brandforge-assets/campaigns/test/sage/narration_abc123.mp3",
    ):
        result = await narrate_agent_milestone(
            milestone="campaign_start",
            campaign_id="test-campaign-123",
            tool_context=mock_tool_context,
        )

    assert result.startswith("gs://")
    assert result.endswith(".mp3")
    assert "sage" in result


# ── DoD Test: Narration caching ────────────────────────────────────────


@pytest.mark.asyncio
async def test_narration_caching(mock_tool_context, mock_tts_response):
    """Calling narrate_agent_milestone twice with same input returns same URL (cache hit)."""
    from brandforge.agents.sage.tools import narrate_agent_milestone

    cached_url = "gs://brandforge-assets/campaigns/test/sage/narration_cached.mp3"

    with patch(
        "brandforge.agents.sage.tools.download_blob",
        return_value=mock_tts_response,  # Cache hit
    ):
        result1 = await narrate_agent_milestone(
            milestone="campaign_start",
            campaign_id="test-campaign-123",
            tool_context=mock_tool_context,
        )
        result2 = await narrate_agent_milestone(
            milestone="campaign_start",
            campaign_id="test-campaign-123",
            tool_context=mock_tool_context,
        )

    # Both calls should return the same URL pattern (cache hit path)
    assert result1.startswith("gs://")
    assert result2.startswith("gs://")
    # Since both use same text, hash is identical → same GCS path
    assert result1 == result2


# ── DoD Test: Voice feedback classified ────────────────────────────────


@pytest.mark.asyncio
async def test_voice_feedback_classified(mock_tool_context, mock_tts_response):
    """Given 'make it more playful', VoiceFeedbackResult.intent should be 'modification'."""
    from brandforge.agents.sage.tools import process_voice_feedback

    mock_client = MagicMock()

    # Transcription response
    transcribe_resp = MagicMock()
    transcribe_resp.text = "make it more playful"

    # Classification response
    classify_resp = MagicMock()
    classify_resp.text = json.dumps({
        "intent": "modification",
        "target_agent": "copy_editor",
        "instruction": "Adjust copy tone to be more playful and conversational",
        "sage_response_text": "Got it — making the copy more playful.",
    })

    mock_client.models.generate_content.side_effect = [transcribe_resp, classify_resp]

    with patch(
        "brandforge.agents.sage.tools._get_genai_client",
        return_value=mock_client,
    ), patch(
        "brandforge.agents.sage.tools.download_blob",
        return_value=b"fake-audio-bytes",
    ), patch(
        "brandforge.agents.sage.tools._synthesize_speech",
        new_callable=AsyncMock,
        return_value=mock_tts_response,
    ), patch(
        "brandforge.agents.sage.tools.upload_blob",
        return_value="gs://brandforge-assets/campaigns/test/sage/response.mp3",
    ):
        result = await process_voice_feedback(
            audio_gcs_url="gs://brandforge-assets/campaigns/test/voice_input.webm",
            campaign_id="test-campaign-123",
            tool_context=mock_tool_context,
        )

    assert result["intent"] == "modification"
    assert result["transcription"] == "make it more playful"


# ── DoD Test: Modification routed to agent ─────────────────────────────


@pytest.mark.asyncio
async def test_modification_routed_to_agent(mock_tool_context, mock_tts_response):
    """A voice modification for copy should be dispatched to copy_editor agent."""
    from brandforge.agents.sage.tools import process_voice_feedback

    mock_client = MagicMock()
    transcribe_resp = MagicMock()
    transcribe_resp.text = "change the copy style to be more professional"

    classify_resp = MagicMock()
    classify_resp.text = json.dumps({
        "intent": "modification",
        "target_agent": "copy_editor",
        "instruction": "Adjust copy to professional tone",
        "sage_response_text": "Adjusting copy tone now.",
    })

    mock_client.models.generate_content.side_effect = [transcribe_resp, classify_resp]

    with patch(
        "brandforge.agents.sage.tools._get_genai_client",
        return_value=mock_client,
    ), patch(
        "brandforge.agents.sage.tools.download_blob",
        return_value=b"fake-audio",
    ), patch(
        "brandforge.agents.sage.tools._synthesize_speech",
        new_callable=AsyncMock,
        return_value=mock_tts_response,
    ), patch(
        "brandforge.agents.sage.tools.upload_blob",
        return_value="gs://bucket/response.mp3",
    ):
        result = await process_voice_feedback(
            audio_gcs_url="gs://bucket/input.webm",
            campaign_id="test-campaign-123",
            tool_context=mock_tool_context,
        )

    assert result["target_agent"] == "copy_editor"
    assert result["instruction"]
    # Verify modification injected into session state
    assert "voice_modification_copy_editor" in mock_tool_context.state


# ── DoD Test: Barge-in handling ────────────────────────────────────────


@pytest.mark.asyncio
async def test_barge_in_handling(mock_tool_context, mock_tts_response):
    """New audio arriving should be processable while narration is 'playing'.

    Since narrations are non-blocking (async), new voice input should
    be processed independently. We verify process_voice_feedback works
    regardless of existing narration state.
    """
    from brandforge.agents.sage.tools import narrate_agent_milestone, process_voice_feedback

    # Simulate a narration already happened
    mock_tool_context.state["sage_narrations"] = [
        {"milestone": "brand_dna_complete", "text": "...", "audio_url": "gs://..."},
    ]

    mock_client = MagicMock()
    transcribe_resp = MagicMock()
    transcribe_resp.text = "stop, I want darker colors"

    classify_resp = MagicMock()
    classify_resp.text = json.dumps({
        "intent": "modification",
        "target_agent": "brand_strategist",
        "instruction": "Use a darker color palette",
        "sage_response_text": "Understood — switching to darker tones.",
    })

    mock_client.models.generate_content.side_effect = [transcribe_resp, classify_resp]

    with patch(
        "brandforge.agents.sage.tools._get_genai_client",
        return_value=mock_client,
    ), patch(
        "brandforge.agents.sage.tools.download_blob",
        return_value=b"barge-in-audio",
    ), patch(
        "brandforge.agents.sage.tools._synthesize_speech",
        new_callable=AsyncMock,
        return_value=mock_tts_response,
    ), patch(
        "brandforge.agents.sage.tools.upload_blob",
        return_value="gs://bucket/barge_in_response.mp3",
    ):
        result = await process_voice_feedback(
            audio_gcs_url="gs://bucket/barge_in.webm",
            campaign_id="test-campaign-123",
            tool_context=mock_tool_context,
        )

    # Barge-in should process successfully despite active narration
    assert result["intent"] == "modification"
    assert result["target_agent"] == "brand_strategist"
    assert "voice_modification_brand_strategist" in mock_tool_context.state
