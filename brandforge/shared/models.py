"""BrandForge shared Pydantic models — ALL schemas live here.

Never define data models inside agent files. Import from this module only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

import re

from pydantic import BaseModel, Field, field_validator

# ── Enums ──────────────────────────────────────────────────────────────────


class CampaignStatus(str, Enum):
    """Lifecycle status of a campaign."""

    PENDING = "pending"
    RUNNING = "running"
    QA_REVIEW = "qa_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"


class AgentStatus(str, Enum):
    """Execution status of a single agent run."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class Platform(str, Enum):
    """Supported social media platforms."""

    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"
    TWITTER_X = "twitter_x"
    FACEBOOK = "facebook"
    YOUTUBE = "youtube"


# ── Core Campaign ───────────────────────────────────────────────────────────


class BrandBrief(BaseModel):
    """Raw input from the user describing their brand and campaign goals."""

    brand_name: str = Field(description="The brand name.")
    product_description: str = Field(description="What the product does.")
    target_audience: str = Field(description="Primary target audience.")
    campaign_goal: str = Field(
        description="Campaign objective, e.g. 'product launch', 'brand awareness'."
    )
    tone_keywords: list[str] = Field(
        description="3-5 adjectives describing desired brand tone."
    )
    platforms: list[Platform] = Field(
        description="Target social platforms for the campaign."
    )
    uploaded_asset_urls: list[str] = Field(
        default_factory=list,
        description="GCS URLs of uploaded logos or reference images.",
    )
    voice_brief_url: str | None = Field(
        default=None,
        description="GCS URL of a spoken voice brief audio file.",
    )


class Campaign(BaseModel):
    """Top-level campaign object stored in Firestore."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    brand_brief: BrandBrief
    status: CampaignStatus = CampaignStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    brand_dna_id: str | None = Field(
        default=None, description="FK → BrandDNA document."
    )
    asset_bundle_id: str | None = Field(
        default=None, description="FK → AssetBundle document."
    )


# ── Agent Execution Tracking ────────────────────────────────────────────────


class AgentRun(BaseModel):
    """Tracks the execution of a single sub-agent for a campaign."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="The campaign this run belongs to.")
    agent_name: str = Field(
        description="Agent identifier, e.g. 'brand_strategist'."
    )
    status: AgentStatus = AgentStatus.IDLE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_ref: str | None = Field(
        default=None, description="GCS path or Firestore doc ID of the output."
    )
    error_message: str | None = None
    retry_count: int = 0


# ── Pub/Sub Message Envelope ────────────────────────────────────────────────


class AgentMessage(BaseModel):
    """Standard A2A message envelope for all Pub/Sub messages."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_agent: str = Field(description="Name of the publishing agent.")
    target_agent: str = Field(description="Name of the subscribing agent.")
    campaign_id: str = Field(description="Campaign this message relates to.")
    event_type: str = Field(
        description="Event identifier, e.g. 'brand_dna_ready', 'qa_failed'."
    )
    payload: dict = Field(  # type: ignore[type-arg]
        default_factory=dict, description="Agent-specific payload data."
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Brand DNA (Phase 1) ────────────────────────────────────────────────────


class ColorPalette(BaseModel):
    """Five-color brand palette. All values must be valid #RRGGBB hex."""

    primary: str = Field(description="Primary brand color, e.g. '#2D3A2E'.")
    secondary: str = Field(description="Secondary brand color.")
    accent: str = Field(description="Accent / highlight color.")
    background: str = Field(description="Background color.")
    text: str = Field(description="Text / body copy color.")

    @field_validator("*")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        """Ensure every color field is a valid hex color code."""
        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError(f"Invalid hex color: {v}")
        return v


class Typography(BaseModel):
    """Font selections and personality description."""

    heading_font: str = Field(description="Heading typeface, e.g. 'Canela Display'.")
    body_font: str = Field(description="Body typeface, e.g. 'Neue Haas Grotesk'.")
    font_personality: str = Field(
        description="Personality of the type system, e.g. 'Editorial, authoritative'."
    )


class AudiencePersona(BaseModel):
    """Primary audience persona derived from the brand brief."""

    name: str = Field(description="Persona name, e.g. 'Urban Eco-Conscious Millennial'.")
    age_range: str = Field(description="Age range, e.g. '25-35'.")
    values: list[str] = Field(description="Core values, e.g. ['sustainability'].")
    pain_points: list[str] = Field(description="Key pain points.")
    content_habits: list[str] = Field(
        description="Content consumption habits, e.g. ['heavy Instagram user']."
    )


class MessagingPillar(BaseModel):
    """A core messaging pillar for the brand."""

    title: str = Field(description="Pillar title, e.g. 'Radical Authenticity'.")
    one_liner: str = Field(description="The core message in one sentence.")
    supporting_points: list[str] = Field(description="Supporting evidence / talking points.")
    avoid: list[str] = Field(description="What NOT to say under this pillar.")


class CompetitorInsight(BaseModel):
    """Competitive analysis — populated only if competitor assets were uploaded."""

    competitor_name: str = Field(description="Competitor brand name.")
    visual_language: str = Field(description="Competitor's visual style.")
    tone: str = Field(description="Competitor's tone of voice.")
    positioning: str = Field(description="Competitor's market positioning.")
    differentiation_opportunity: str = Field(
        description="How this brand can differentiate."
    )


class BrandDNA(BaseModel):
    """The master brand document. All downstream agents reference this."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="FK → Campaign document.")
    version: int = Field(default=1, description="Version number (increments, never overwrites).")
    brand_name: str = Field(description="The brand name.")
    brand_essence: str = Field(description="One-sentence brand soul.")
    brand_personality: list[str] = Field(description="Up to 5 personality adjectives.")
    tone_of_voice: str = Field(description="Detailed tone paragraph.")
    color_palette: ColorPalette
    typography: Typography
    primary_persona: AudiencePersona
    messaging_pillars: list[MessagingPillar] = Field(
        description="Up to 3 messaging pillars."
    )
    visual_direction: str = Field(
        description="Paragraph describing visual direction for image/video agents."
    )
    platform_strategy: dict[str, str] = Field(  # type: ignore[type-arg]
        description="Platform name → content approach mapping."
    )
    competitor_insights: list[CompetitorInsight] = Field(default_factory=list)
    do_not_use: list[str] = Field(description="Forbidden words / themes.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_brief_summary: str = Field(
        description="Grounding: summarises what brief inputs were provided."
    )


class VisualAssetAnalysis(BaseModel):
    """Output of the analyze_brand_assets tool."""

    detected_colors: list[str] = Field(description="Hex colors found in uploaded assets.")
    typography_style: str = Field(description="Detected typography style.")
    visual_energy: str = Field(
        description="Visual energy level, e.g. 'minimalist', 'maximalist'."
    )
    existing_brand_elements: list[str] = Field(
        description="Recognised brand elements (logo mark, patterns, etc.)."
    )
    recommended_direction: str = Field(
        description="Recommended visual direction based on asset analysis."
    )
