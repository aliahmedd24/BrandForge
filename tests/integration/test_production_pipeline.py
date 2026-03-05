"""Integration tests — Phase 2 Production Pipeline.

Tests the orchestrator's coordination of all 6 agents and
verifies completion event publishing.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.agents.orchestrator.tools import (
    check_pipeline_status,
    finalize_production,
    launch_production_pipeline,
)
from brandforge.shared.models import AgentStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BRAND_DNA: dict = {
    "id": str(uuid.uuid4()),
    "campaign_id": "camp-001",
    "version": 1,
    "brand_name": "Earthbrew",
    "brand_essence": "Coffee.",
    "brand_personality": ["warm"],
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
    "visual_direction": "Warm tones.",
    "platform_strategy": {"instagram": "Lifestyle"},
    "do_not_use": [],
    "source_brief_summary": "Earthbrew.",
}


# ---------------------------------------------------------------------------
# Test 1: Parallel execution — all 6 agents dispatched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_execution() -> None:
    """All 6 agents get AgentRun records created (verifies parallel dispatch)."""
    mock_get_doc = AsyncMock(return_value=SAMPLE_BRAND_DNA)
    mock_create_doc = AsyncMock(return_value="doc-id")
    mock_update_doc = AsyncMock()

    with (
        patch("brandforge.shared.firestore.get_document", mock_get_doc),
        patch("brandforge.shared.firestore.create_document", mock_create_doc),
        patch("brandforge.shared.firestore.update_document", mock_update_doc),
    ):
        result = await launch_production_pipeline(
            campaign_id="camp-001",
            brand_dna_id=SAMPLE_BRAND_DNA["id"],
        )

    assert result["status"] == "success"

    # Verify all 6 agents were initialized
    agent_runs = result["agent_runs"]
    agent_names = {r["agent_name"] for r in agent_runs}
    expected_agents = {
        "scriptwriter", "mood_board_director", "virtual_tryon",
        "copy_editor", "video_producer", "image_generator",
    }
    assert agent_names == expected_agents

    # Verify 6 create_document calls (one per agent) + campaign update
    assert mock_create_doc.call_count == 6

    # Verify wave structure in response
    assert set(result["wave_1"]) == {"scriptwriter", "mood_board_director", "virtual_tryon"}
    assert set(result["wave_2"]) == {"copy_editor", "video_producer", "image_generator"}


# ---------------------------------------------------------------------------
# Test 2: All completion events published
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_completion_events_published() -> None:
    """finalize_production publishes production_complete after all agents done."""
    # Mock all agents as complete
    completed_runs = [
        {"agent_name": name, "status": AgentStatus.COMPLETE, "campaign_id": "camp-001"}
        for name in [
            "scriptwriter", "mood_board_director", "virtual_tryon",
            "copy_editor", "video_producer", "image_generator",
        ]
    ]
    mock_query = AsyncMock(return_value=completed_runs)
    mock_update = AsyncMock()
    mock_publish = AsyncMock(return_value="msg-final")

    with (
        patch("brandforge.shared.firestore.query_collection", mock_query),
        patch("brandforge.shared.firestore.update_document", mock_update),
        patch("brandforge.shared.pubsub.publish_message", mock_publish),
    ):
        result = await finalize_production(campaign_id="camp-001")

    assert result["status"] == "success"
    assert result["failures"] == []

    # Verify production_complete event was published
    mock_publish.assert_called_once()
    call_kwargs = mock_publish.call_args[1]
    published_msg = call_kwargs["message"]
    assert published_msg.event_type == "production_complete"
    assert published_msg.source_agent == "orchestrator"
    assert published_msg.campaign_id == "camp-001"
