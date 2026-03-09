"""Shared Pydantic data models for BrandForge.

All schemas used across agents and infrastructure live here.
Never define schemas inside agent files — import from this module.
"""

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────


class CampaignStatus(str, Enum):
    """Lifecycle states of a marketing campaign."""

    PENDING = "pending"
    RUNNING = "running"
    QA_REVIEW = "qa_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"


class AgentStatus(str, Enum):
    """Execution states of a single agent run."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class Platform(str, Enum):
    """Supported social media platforms for content distribution."""

    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"
    TWITTER_X = "twitter_x"
    FACEBOOK = "facebook"
    YOUTUBE = "youtube"


# ── Utility ────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _uuid() -> str:
    """Return a new UUID4 as a string."""
    return str(uuid.uuid4())


# ── Core Campaign ───────────────────────────────────────────────────────────


class BrandBrief(BaseModel):
    """Raw input from the user describing their brand and campaign goals."""

    brand_name: str
    product_description: str
    target_audience: str
    campaign_goal: str  # e.g. "product launch", "brand awareness"
    tone_keywords: list[str]  # e.g. ["bold", "sustainable", "urban"]
    platforms: list[Platform]
    uploaded_asset_urls: list[str] = []  # GCS URLs of uploaded logos/images
    voice_brief_url: Optional[str] = None  # GCS URL of spoken brief audio


class Campaign(BaseModel):
    """Top-level campaign object stored in Firestore."""

    id: str = Field(default_factory=_uuid)
    brand_brief: BrandBrief
    status: CampaignStatus = CampaignStatus.PENDING
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    brand_dna_id: Optional[str] = None  # FK → BrandDNA document
    asset_bundle_id: Optional[str] = None  # FK → AssetBundle document


# ── Agent Execution Tracking ────────────────────────────────────────────────


class AgentRun(BaseModel):
    """Tracks the execution of a single sub-agent for a campaign."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    agent_name: str  # e.g. "brand_strategist"
    status: AgentStatus = AgentStatus.IDLE
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_ref: Optional[str] = None  # GCS path or Firestore doc ID
    error_message: Optional[str] = None
    retry_count: int = 0


# ── A2A Message Payload ──────────────────────────────────────────────────────


class AgentMessage(BaseModel):
    """Payload passed between agents via ADK A2A (RemoteA2aAgent).

    For cross-service calls (e.g. Analytics Agent → Orchestrator), this
    payload is serialized as the message body. For same-deployment agents,
    pass via session state or output_key instead.
    """

    message_id: str = Field(default_factory=_uuid)
    source_agent: str
    target_agent: str
    campaign_id: str
    event_type: str  # e.g. "analytics_insights_ready"
    payload: dict  # Agent-specific payload
    timestamp: datetime = Field(default_factory=_utcnow)


# ── Brand DNA Models (Phase 1) ──────────────────────────────────────────


class ColorPalette(BaseModel):
    """Five-color brand palette with hex validation."""

    primary: str  # e.g. "#2D3A2E"
    secondary: str
    accent: str
    background: str
    text: str

    @field_validator("*")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        """Ensure every color field is a valid hex color code."""
        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError(f"Invalid hex color: {v}")
        return v


class Typography(BaseModel):
    """Brand typography specification."""

    heading_font: str  # e.g. "Canela Display"
    body_font: str  # e.g. "Neue Haas Grotesk"
    font_personality: str  # e.g. "Editorial, high-fashion, authoritative"


class AudiencePersona(BaseModel):
    """Primary target audience persona."""

    name: str  # e.g. "Urban Eco-Conscious Millennial"
    age_range: str  # e.g. "25-35"
    values: list[str]  # e.g. ["sustainability", "authenticity"]
    pain_points: list[str]
    content_habits: list[str]  # e.g. ["heavy Instagram user"]


class MessagingPillar(BaseModel):
    """A core messaging pillar for the brand."""

    title: str  # e.g. "Radical Authenticity"
    one_liner: str  # The core message
    supporting_points: list[str]
    avoid: list[str]  # What NOT to say


class CompetitorInsight(BaseModel):
    """Competitive analysis insight. Populated only if competitor assets were uploaded."""

    competitor_name: str
    visual_language: str
    tone: str
    positioning: str
    differentiation_opportunity: str


class VisualAssetAnalysis(BaseModel):
    """Output of the analyze_brand_assets tool."""

    detected_colors: list[str]
    typography_style: str
    visual_energy: str  # e.g. "minimalist", "maximalist", "editorial"
    existing_brand_elements: list[str]
    recommended_direction: str


class BrandDNA(BaseModel):
    """The master brand document. All downstream agents reference this."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    version: int = 1
    brand_name: str
    brand_essence: str  # 1-sentence brand soul
    brand_personality: list[str]  # 5 adjectives max
    tone_of_voice: str  # Paragraph description
    color_palette: ColorPalette
    typography: Typography
    primary_persona: AudiencePersona
    messaging_pillars: list[MessagingPillar]  # 3 pillars max
    visual_direction: str  # Paragraph for image/video agents
    platform_strategy: dict[str, str]  # Platform → content approach
    competitor_insights: list[CompetitorInsight] = []
    do_not_use: list[str]  # Forbidden words/themes
    created_at: datetime = Field(default_factory=_utcnow)
    source_brief_summary: str  # Grounding: what was the input
