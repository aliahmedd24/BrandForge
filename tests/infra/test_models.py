"""Tests for Pydantic model serialization/deserialization."""

import json
from datetime import datetime, timezone

from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    BrandBrief,
    Campaign,
    CampaignStatus,
    Platform,
)


class TestEnums:
    """Verify enum values and string serialization."""

    def test_campaign_status_values(self) -> None:
        """All expected CampaignStatus values exist."""
        assert CampaignStatus.PENDING == "pending"
        assert CampaignStatus.RUNNING == "running"
        assert CampaignStatus.QA_REVIEW == "qa_review"
        assert CampaignStatus.APPROVED == "approved"
        assert CampaignStatus.PUBLISHED == "published"
        assert CampaignStatus.FAILED == "failed"

    def test_agent_status_values(self) -> None:
        """All expected AgentStatus values exist."""
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.RUNNING == "running"
        assert AgentStatus.COMPLETE == "complete"
        assert AgentStatus.FAILED == "failed"

    def test_platform_values(self) -> None:
        """All expected Platform values exist."""
        expected = {"instagram", "linkedin", "tiktok", "twitter_x", "facebook", "youtube"}
        actual = {p.value for p in Platform}
        assert actual == expected


class TestBrandBrief:
    """Verify BrandBrief serialization."""

    def test_round_trip(self, sample_brand_brief: BrandBrief) -> None:
        """BrandBrief serializes to JSON and deserializes back identically."""
        json_str = sample_brand_brief.model_dump_json()
        restored = BrandBrief.model_validate_json(json_str)
        assert restored == sample_brand_brief

    def test_optional_fields_default(self) -> None:
        """Optional fields default correctly."""
        brief = BrandBrief(
            brand_name="X",
            product_description="Y",
            target_audience="Z",
            campaign_goal="awareness",
            tone_keywords=["fun"],
            platforms=[Platform.TIKTOK],
        )
        assert brief.uploaded_asset_urls == []
        assert brief.voice_brief_url is None


class TestCampaign:
    """Verify Campaign serialization and defaults."""

    def test_round_trip(self, sample_campaign: Campaign) -> None:
        """Campaign serializes to JSON and deserializes back."""
        json_str = sample_campaign.model_dump_json()
        restored = Campaign.model_validate_json(json_str)
        assert restored.brand_brief == sample_campaign.brand_brief
        assert restored.status == CampaignStatus.PENDING

    def test_uuid_auto_generated(self, sample_campaign: Campaign) -> None:
        """Campaign ID is auto-generated as a valid UUID string."""
        assert len(sample_campaign.id) == 36  # UUID4 format
        assert "-" in sample_campaign.id

    def test_timestamps_are_utc(self, sample_campaign: Campaign) -> None:
        """Timestamps are timezone-aware UTC."""
        assert sample_campaign.created_at.tzinfo is not None
        assert sample_campaign.created_at.tzinfo == timezone.utc

    def test_default_status_is_pending(self, sample_campaign: Campaign) -> None:
        """Default campaign status is PENDING."""
        assert sample_campaign.status == CampaignStatus.PENDING

    def test_dict_serialization(self, sample_campaign: Campaign) -> None:
        """Campaign can be converted to a dict (for Firestore)."""
        data = sample_campaign.model_dump(mode="json")
        assert isinstance(data, dict)
        assert data["status"] == "pending"
        assert isinstance(data["created_at"], str)


class TestAgentRun:
    """Verify AgentRun serialization."""

    def test_round_trip(self) -> None:
        """AgentRun serializes and deserializes correctly."""
        run = AgentRun(campaign_id="abc-123", agent_name="brand_strategist")
        json_str = run.model_dump_json()
        restored = AgentRun.model_validate_json(json_str)
        assert restored.campaign_id == "abc-123"
        assert restored.agent_name == "brand_strategist"
        assert restored.status == AgentStatus.IDLE
        assert restored.retry_count == 0

    def test_uuid_auto_generated(self) -> None:
        """AgentRun ID is auto-generated."""
        run = AgentRun(campaign_id="x", agent_name="y")
        assert len(run.id) == 36


class TestAgentMessage:
    """Verify AgentMessage serialization."""

    def test_round_trip(self) -> None:
        """AgentMessage serializes and deserializes correctly."""
        msg = AgentMessage(
            source_agent="analytics",
            target_agent="orchestrator",
            campaign_id="camp-1",
            event_type="analytics_insights_ready",
            payload={"score": 0.95, "insights": ["trending topic"]},
        )
        json_str = msg.model_dump_json()
        restored = AgentMessage.model_validate_json(json_str)
        assert restored.source_agent == "analytics"
        assert restored.payload["score"] == 0.95

    def test_timestamp_is_utc(self) -> None:
        """AgentMessage timestamp is timezone-aware UTC."""
        msg = AgentMessage(
            source_agent="a",
            target_agent="b",
            campaign_id="c",
            event_type="test",
            payload={},
        )
        assert msg.timestamp.tzinfo == timezone.utc
