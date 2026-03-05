"""Tests for Pub/Sub connectivity and message publishing.

These tests require live Pub/Sub topics. They will be marked
[UNVERIFIED] if GCP is not configured.
"""

from __future__ import annotations

import pytest

from brandforge.shared.config import PUBSUB_TOPIC_CAMPAIGN_CREATED
from brandforge.shared.models import AgentMessage
from brandforge.shared.pubsub import publish_message


@pytest.mark.asyncio
async def test_pubsub_publish_agent_message() -> None:
    """Can publish an AgentMessage to the campaign.created topic."""
    msg = AgentMessage(
        source_agent="test_runner",
        target_agent="orchestrator",
        campaign_id="test-campaign-001",
        event_type="campaign_created",
        payload={"test": True},
    )

    message_id = await publish_message(PUBSUB_TOPIC_CAMPAIGN_CREATED, msg)
    assert message_id  # Non-empty string = successfully published
