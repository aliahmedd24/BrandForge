"""BrandForge shared Pydantic models — ALL schemas live here.

Never define data models inside agent files. Import from this module only.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# ── Enums ──────────────────────────────────────────────────────────────────


class CampaignStatus(StrEnum):
    """Lifecycle status of a campaign."""

    PENDING = "pending"
    RUNNING = "running"
    QA_REVIEW = "qa_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"


class AgentStatus(StrEnum):
    """Execution status of a single agent run."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class Platform(StrEnum):
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


# ── Phase 2: Creative Production ──────────────────────────────────────────


class SceneDirection(BaseModel):
    """A single scene in a video script with visual and audio direction."""

    scene_number: int = Field(ge=1, description="Scene sequence number starting at 1.")
    duration_seconds: int = Field(
        ge=1, le=60, description="Duration of this scene in seconds."
    )
    visual_description: str = Field(
        description="Detailed description of what appears on screen. "
        "Must be specific enough for Veo to generate the scene."
    )
    voiceover: str = Field(description="Exact narration text for this scene.")
    text_overlay: str | None = Field(
        default=None, description="On-screen text overlay, if any."
    )
    emotion: str = Field(
        description="Intended emotional beat, e.g. 'warm', 'urgent', 'aspirational'."
    )


class VideoScript(BaseModel):
    """A complete video script for a specific platform and duration."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="FK → Campaign document.")
    platform: Platform = Field(description="Target platform for this script.")
    duration_seconds: int = Field(
        description="Total duration: 15, 30, or 60 seconds."
    )
    aspect_ratio: str = Field(
        description="Video aspect ratio: '9:16', '1:1', or '16:9'."
    )
    hook: str = Field(
        max_length=200,
        description="First 3 seconds hook — must grab attention immediately.",
    )
    scenes: list[SceneDirection] = Field(
        description="Ordered list of scene directions."
    )
    cta: str = Field(
        max_length=100, description="Call to action text."
    )
    brand_dna_version: int = Field(
        description="Version of the BrandDNA document used for generation."
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("scenes")
    @classmethod
    def validate_scenes_not_empty(cls, v: list[SceneDirection]) -> list[SceneDirection]:
        """Ensure at least one scene exists in the script."""
        if not v:
            raise ValueError("VideoScript must have at least one scene.")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        """Ensure duration is one of the allowed values."""
        if v not in (15, 30, 60):
            raise ValueError(f"Duration must be 15, 30, or 60. Got {v}.")
        return v


class ImageSpec(BaseModel):
    """Platform-specific image generation specification."""

    platform: Platform = Field(description="Target platform.")
    width: int = Field(ge=100, le=4096, description="Image width in pixels.")
    height: int = Field(ge=100, le=4096, description="Image height in pixels.")
    aspect_ratio: str = Field(description="Aspect ratio string, e.g. '1:1', '9:16'.")
    use_case: str = Field(
        description="Image use case: 'feed_post', 'story', 'banner', 'reel_cover'."
    )

    @classmethod
    def default_specs_for_platform(cls, platform: Platform) -> list[ImageSpec]:
        """Return the default image specs for a given platform per PRD table."""
        specs_map: dict[Platform, list[dict]] = {  # type: ignore[type-arg]
            Platform.INSTAGRAM: [
                {"width": 1080, "height": 1080, "aspect_ratio": "1:1", "use_case": "feed_post"},
                {"width": 1080, "height": 1920, "aspect_ratio": "9:16", "use_case": "story"},
            ],
            Platform.LINKEDIN: [
                {"width": 1200, "height": 627, "aspect_ratio": "16:9", "use_case": "feed_post"},
            ],
            Platform.TWITTER_X: [
                {"width": 1600, "height": 900, "aspect_ratio": "16:9", "use_case": "feed_post"},
            ],
            Platform.FACEBOOK: [
                {"width": 1080, "height": 1080, "aspect_ratio": "1:1", "use_case": "feed_post"},
                {"width": 1200, "height": 630, "aspect_ratio": "16:9", "use_case": "banner"},
            ],
            Platform.TIKTOK: [
                {"width": 1080, "height": 1920, "aspect_ratio": "9:16", "use_case": "feed_post"},
            ],
            Platform.YOUTUBE: [
                {"width": 1280, "height": 720, "aspect_ratio": "16:9", "use_case": "thumbnail"},
            ],
        }
        return [
            cls(platform=platform, **spec)
            for spec in specs_map.get(platform, [])
        ]


class GeneratedImage(BaseModel):
    """A production image generated via Imagen 4.0 Ultra."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="FK → Campaign document.")
    platform: Platform = Field(description="Target platform.")
    spec: ImageSpec = Field(description="The image spec used for generation.")
    gcs_url: str = Field(description="GCS URL of the generated image.")
    variant_number: int = Field(
        ge=1, le=3, description="Variant number (1=A, 2=B, 3=C) for A/B testing."
    )
    generation_prompt: str = Field(
        description="Full Imagen prompt used — stored for QA traceability."
    )
    brand_dna_version: int = Field(
        description="Version of the BrandDNA document used."
    )
    qa_status: str = Field(default="pending", description="QA status: pending/approved/rejected.")
    qa_score: float | None = Field(default=None, ge=0.0, le=1.0, description="QA score 0.0-1.0.")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VoiceConfig(BaseModel):
    """Cloud TTS voice configuration for voiceover generation."""

    language_code: str = Field(default="en-US", description="BCP-47 language code.")
    voice_name: str = Field(
        default="en-US-Neural2-D",
        description="Cloud TTS voice name. Default: warm male Neural2 voice.",
    )
    speaking_rate: float = Field(
        default=1.0, ge=0.25, le=4.0, description="Speech rate multiplier."
    )
    pitch: float = Field(
        default=0.0, ge=-20.0, le=20.0, description="Pitch shift in semitones."
    )


class GeneratedVideo(BaseModel):
    """A video asset generated via Veo 3.1 with Cloud TTS voiceover."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="FK → Campaign document.")
    script_id: str = Field(description="FK → VideoScript document.")
    platform: Platform = Field(description="Target platform.")
    duration_seconds: int = Field(description="Video duration in seconds.")
    aspect_ratio: str = Field(description="Video aspect ratio.")
    gcs_url_raw: str = Field(description="GCS URL of Veo raw output (no audio).")
    gcs_url_final: str = Field(
        default="", description="GCS URL of final video with voiceover."
    )
    operation_id: str = Field(description="Veo operation ID for tracking.")
    generation_status: str = Field(
        default="pending",
        description="Generation status: pending/processing/complete/failed.",
    )
    voice_config: VoiceConfig = Field(
        default_factory=VoiceConfig, description="TTS configuration used."
    )
    qa_status: str = Field(default="pending", description="QA status: pending/approved/rejected.")
    qa_score: float | None = Field(default=None, ge=0.0, le=1.0, description="QA score 0.0-1.0.")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlatformCopy(BaseModel):
    """Platform-specific marketing copy bundle."""

    platform: Platform = Field(description="Target platform.")
    caption: str = Field(description="Main post caption text.")
    headline: str = Field(max_length=150, description="Post headline or title.")
    hashtags: list[str] = Field(description="Hashtags (platform limits enforced by validator).")
    cta_text: str = Field(max_length=50, description="Call-to-action text.")
    character_count: int = Field(ge=0, description="Total caption character count.")
    brand_voice_score: float = Field(
        ge=0.0, le=1.0,
        description="Brand voice alignment score (0.0-1.0), self-assessed by Gemini.",
    )

    @field_validator("hashtags")
    @classmethod
    def validate_hashtag_limits(cls, v: list[str], info) -> list[str]:  # type: ignore[type-arg]
        """Enforce platform-specific hashtag count limits."""
        platform = info.data.get("platform")
        if platform == Platform.INSTAGRAM and len(v) > 30:
            raise ValueError(f"Instagram max 30 hashtags, got {len(v)}.")
        if platform == Platform.LINKEDIN and len(v) > 5:
            raise ValueError(f"LinkedIn max 5 hashtags, got {len(v)}.")
        return v

    @field_validator("caption")
    @classmethod
    def validate_caption_length(cls, v: str, info) -> str:  # type: ignore[type-arg]
        """Enforce platform-specific caption character limits."""
        platform = info.data.get("platform")
        limits = {
            Platform.INSTAGRAM: 2200,
            Platform.TWITTER_X: 280,
            Platform.LINKEDIN: 3000,
            Platform.TIKTOK: 2200,
            Platform.FACEBOOK: 63206,
            Platform.YOUTUBE: 5000,
        }
        max_len = limits.get(platform, 5000)
        if len(v) > max_len:
            raise ValueError(
                f"{platform} caption max {max_len} chars, got {len(v)}."
            )
        return v


class CopyPackage(BaseModel):
    """Complete marketing copy package for all platforms in a campaign."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="FK → Campaign document.")
    platform_copies: list[PlatformCopy] = Field(
        description="Per-platform copy bundles."
    )
    global_tagline: str = Field(
        max_length=100, description="Campaign tagline — one memorable line."
    )
    press_blurb: str = Field(
        max_length=700, description="100-word brand description for press."
    )
    qa_status: str = Field(default="pending", description="QA status: pending/approved/rejected.")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GeneratedTryOn(BaseModel):
    """A virtual try-on image generated via virtual-try-on-001."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="FK → Campaign document.")
    product_image_gcs: str = Field(description="GCS URL of the product garment image.")
    model_image_gcs: str = Field(description="GCS URL of the model reference image.")
    gcs_url: str = Field(description="GCS URL of the generated try-on image.")
    variant_number: int = Field(
        ge=1, le=3, description="Variant number for this combination."
    )
    qa_status: str = Field(default="pending", description="QA status: pending/approved/rejected.")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MoodBoardImage(BaseModel):
    """A single reference image in a mood board."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = Field(description="FK → Campaign document.")
    category: str = Field(
        description="Image category: 'lifestyle', 'texture', 'typography', 'color_palette'."
    )
    gcs_url: str = Field(description="GCS URL of the reference image.")
    generation_prompt: str = Field(
        description="Prompt used to generate this image."
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
