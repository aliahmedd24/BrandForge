"""Tests for Pydantic model serialization and validation.

These tests run without any GCP services — pure unit tests.
"""

from __future__ import annotations

import json
from datetime import datetime

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
    """Verify enum values and string representation."""

    def test_campaign_status_values(self) -> None:
        """All CampaignStatus values should be valid strings."""
        assert CampaignStatus.PENDING == "pending"
        assert CampaignStatus.RUNNING == "running"
        assert CampaignStatus.QA_REVIEW == "qa_review"
        assert CampaignStatus.APPROVED == "approved"
        assert CampaignStatus.PUBLISHED == "published"
        assert CampaignStatus.FAILED == "failed"

    def test_agent_status_values(self) -> None:
        """All AgentStatus values should be valid strings."""
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.RUNNING == "running"
        assert AgentStatus.COMPLETE == "complete"
        assert AgentStatus.FAILED == "failed"

    def test_platform_values(self) -> None:
        """All Platform enum members should be valid strings."""
        assert Platform.INSTAGRAM == "instagram"
        assert Platform.LINKEDIN == "linkedin"
        assert Platform.TIKTOK == "tiktok"
        assert Platform.TWITTER_X == "twitter_x"
        assert Platform.FACEBOOK == "facebook"
        assert Platform.YOUTUBE == "youtube"


class TestBrandBrief:
    """Validate BrandBrief creation and serialization."""

    def test_brand_brief_minimal(self) -> None:
        """BrandBrief with required fields only should serialize correctly."""
        brief = BrandBrief(
            brand_name="TestBrand",
            product_description="A test product",
            target_audience="Developers",
            campaign_goal="brand awareness",
            tone_keywords=["bold", "modern"],
            platforms=[Platform.INSTAGRAM, Platform.LINKEDIN],
        )
        data = brief.model_dump()
        assert data["brand_name"] == "TestBrand"
        assert data["uploaded_asset_urls"] == []
        assert data["voice_brief_url"] is None

    def test_brand_brief_full(self) -> None:
        """BrandBrief with all fields should round-trip through JSON."""
        brief = BrandBrief(
            brand_name="Grounded",
            product_description="Sustainable outdoor gear",
            target_audience="Eco-conscious millennials",
            campaign_goal="product launch",
            tone_keywords=["sustainable", "bold", "urban"],
            platforms=[Platform.INSTAGRAM, Platform.TIKTOK],
            uploaded_asset_urls=["gs://bucket/logo.png"],
            voice_brief_url="gs://bucket/brief.webm",
        )
        json_str = brief.model_dump_json()
        rebuilt = BrandBrief.model_validate_json(json_str)
        assert rebuilt.brand_name == "Grounded"
        assert rebuilt.voice_brief_url == "gs://bucket/brief.webm"
        assert len(rebuilt.platforms) == 2


class TestCampaign:
    """Validate Campaign creation and defaults."""

    def test_campaign_defaults(self) -> None:
        """Campaign should auto-generate ID, timestamps, and default status."""
        brief = BrandBrief(
            brand_name="Test",
            product_description="Testing",
            target_audience="QA",
            campaign_goal="test",
            tone_keywords=["test"],
            platforms=[Platform.INSTAGRAM],
        )
        campaign = Campaign(brand_brief=brief)
        assert campaign.id  # UUID auto-generated
        assert campaign.status == CampaignStatus.PENDING
        assert isinstance(campaign.created_at, datetime)
        assert campaign.brand_dna_id is None
        assert campaign.asset_bundle_id is None

    def test_campaign_json_round_trip(self) -> None:
        """Campaign should survive JSON serialization and deserialization."""
        brief = BrandBrief(
            brand_name="RoundTrip",
            product_description="Testing round trip",
            target_audience="Engineers",
            campaign_goal="test",
            tone_keywords=["precise"],
            platforms=[Platform.LINKEDIN],
        )
        campaign = Campaign(brand_brief=brief, status=CampaignStatus.RUNNING)
        json_str = campaign.model_dump_json()
        rebuilt = Campaign.model_validate_json(json_str)
        assert rebuilt.id == campaign.id
        assert rebuilt.status == CampaignStatus.RUNNING
        assert rebuilt.brand_brief.brand_name == "RoundTrip"


class TestAgentRun:
    """Validate AgentRun creation and serialization."""

    def test_agent_run_defaults(self) -> None:
        """AgentRun should auto-generate ID and default to IDLE status."""
        run = AgentRun(campaign_id="camp-123", agent_name="brand_strategist")
        assert run.id  # UUID auto-generated
        assert run.status == AgentStatus.IDLE
        assert run.retry_count == 0
        assert run.error_message is None

    def test_agent_run_json_round_trip(self) -> None:
        """AgentRun should survive JSON round trip."""
        run = AgentRun(
            campaign_id="camp-456",
            agent_name="image_generator",
            status=AgentStatus.RUNNING,
            retry_count=2,
        )
        json_str = run.model_dump_json()
        rebuilt = AgentRun.model_validate_json(json_str)
        assert rebuilt.agent_name == "image_generator"
        assert rebuilt.status == AgentStatus.RUNNING
        assert rebuilt.retry_count == 2


class TestAgentMessage:
    """Validate AgentMessage envelope creation and serialization."""

    def test_agent_message_defaults(self) -> None:
        """AgentMessage should auto-generate ID and timestamp."""
        msg = AgentMessage(
            source_agent="brand_strategist",
            target_agent="orchestrator",
            campaign_id="camp-789",
            event_type="brand_dna_ready",
            payload={"brand_dna_id": "dna-001"},
        )
        assert msg.message_id  # UUID auto-generated
        assert isinstance(msg.timestamp, datetime)
        assert msg.payload["brand_dna_id"] == "dna-001"

    def test_agent_message_json_round_trip(self) -> None:
        """AgentMessage should survive JSON round trip."""
        msg = AgentMessage(
            source_agent="qa_inspector",
            target_agent="image_generator",
            campaign_id="camp-abc",
            event_type="qa_failed",
            payload={"asset_id": "img-001", "reason": "off-brand colors"},
        )
        json_str = msg.model_dump_json()
        rebuilt = AgentMessage.model_validate_json(json_str)
        assert rebuilt.event_type == "qa_failed"
        assert rebuilt.payload["reason"] == "off-brand colors"

    def test_agent_message_to_dict_for_pubsub(self) -> None:
        """model_dump(mode='json') should produce a JSON-serializable dict."""
        msg = AgentMessage(
            source_agent="copy_editor",
            target_agent="assembler",
            campaign_id="camp-xyz",
            event_type="copy_ready",
        )
        data = msg.model_dump(mode="json")
        json_bytes = json.dumps(data).encode("utf-8")
        assert len(json_bytes) > 0
        parsed = json.loads(json_bytes)
        assert parsed["source_agent"] == "copy_editor"
