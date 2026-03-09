"""Tests for Pub/Sub publisher helpers.

Tests marked with @pytest.mark.gcp require live Pub/Sub access.
Run with: pytest -m gcp
"""

import json

import pytest

from brandforge.shared.config import settings
from brandforge.shared.pubsub import publish_message


@pytest.mark.gcp
class TestPubSubOperations:
    """Integration tests for Pub/Sub publish operations."""

    def test_publish_campaign_created(self) -> None:
        """Publish a campaign.created message and get a message ID back."""
        payload = {
            "campaign_id": "test-campaign-001",
            "event": "campaign.created",
        }

        message_id = publish_message(
            topic_name=settings.pubsub_campaign_created_topic,
            data=payload,
        )

        assert isinstance(message_id, str)
        assert len(message_id) > 0

    def test_publish_with_attributes(self) -> None:
        """Publish with optional message attributes."""
        payload = {"campaign_id": "test-campaign-002"}

        message_id = publish_message(
            topic_name=settings.pubsub_campaign_created_topic,
            data=payload,
            source="test",
            environment="ci",
        )

        assert isinstance(message_id, str)

    def test_payload_is_json_serializable(self) -> None:
        """Verify test payloads are valid JSON (offline check)."""
        payload = {
            "campaign_id": "test-campaign-003",
            "event": "campaign.created",
            "nested": {"key": "value"},
        }
        serialized = json.dumps(payload, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["campaign_id"] == "test-campaign-003"
