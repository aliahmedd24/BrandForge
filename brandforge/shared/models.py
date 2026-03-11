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


# ── Creative Production Models (Phase 2) ──────────────────────────────


class SceneDirection(BaseModel):
    """A single scene within a video script."""

    scene_number: int
    duration_seconds: int
    visual_description: str  # What to show on screen
    voiceover: str  # Exact narration text
    text_overlay: Optional[str] = None  # On-screen text
    emotion: str  # Intended emotional beat


class VideoScript(BaseModel):
    """A complete video script for a specific platform and duration."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    platform: Platform
    duration_seconds: int  # 15, 30, or 60
    aspect_ratio: str  # "9:16", "1:1", "16:9"
    hook: str  # First 3 seconds
    scenes: list[SceneDirection]
    cta: str  # Call to action
    brand_dna_version: int  # Which BrandDNA version used


class ImageSpec(BaseModel):
    """Specification for a platform-specific image asset."""

    platform: Platform
    width: int
    height: int
    aspect_ratio: str
    use_case: str  # "feed_post", "story", "banner"


class GeneratedImage(BaseModel):
    """A generated image asset with GCS location and QA tracking."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    platform: Platform
    spec: ImageSpec
    gcs_url: str
    variant_number: int  # 1, 2, or 3 (A/B/C)
    generation_prompt: str  # Stored for QA agent reference
    brand_dna_version: int
    qa_status: str = "pending"
    qa_score: Optional[float] = None


class VoiceConfig(BaseModel):
    """Configuration for Cloud TTS voiceover generation."""

    language_code: str = "en-US"
    voice_name: str = "en-US-Neural2-D"  # Default warm male voice
    speaking_rate: float = 1.0
    pitch: float = 0.0


class GeneratedVideo(BaseModel):
    """A generated video asset with raw and final GCS locations."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    script_id: str
    platform: Platform
    duration_seconds: int
    aspect_ratio: str
    gcs_url_raw: str  # Veo output (no audio)
    gcs_url_final: str  # With voiceover
    operation_id: str  # Veo operation ID
    generation_status: str  # "pending" | "processing" | "complete" | "failed"
    qa_status: str = "pending"
    qa_score: Optional[float] = None


class PlatformCopy(BaseModel):
    """Refined copy for a single platform."""

    platform: Platform
    caption: str
    headline: str
    hashtags: list[str]  # Max: 30 for Instagram, 5 for LinkedIn
    cta_text: str
    character_count: int
    brand_voice_score: float  # 0.0-1.0, self-assessed


class CopyPackage(BaseModel):
    """Complete copy package across all platforms."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    platform_copies: list[PlatformCopy]
    global_tagline: str
    press_blurb: str  # 100-word brand description
    qa_status: str = "pending"


# ── QA & Assembly Models (Phase 3) ──────────────────────────────────


class QAViolation(BaseModel):
    """A single specific violation found during QA."""

    category: str  # "color", "typography", "tone", "forbidden_word", "visual_energy"
    severity: str  # "critical" | "moderate" | "minor"
    description: str  # Specific, actionable description
    location: Optional[str] = None  # For video: "0:12-0:18", for image: "bottom-left quadrant"
    expected: str  # What Brand DNA specifies
    found: str  # What was actually generated


class QAResult(BaseModel):
    """Structured QA assessment for a single campaign asset."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    asset_id: str
    asset_type: str  # "image" | "video" | "copy"

    # Scoring (0.0–1.0)
    overall_score: float
    color_compliance: float
    tone_compliance: float
    visual_energy_compliance: float
    messaging_compliance: float = 0.0  # copy only

    # Result
    status: str  # "approved" | "failed" | "escalated"
    violations: list[QAViolation] = []
    approver_notes: str

    # Regeneration
    correction_prompt: Optional[str] = None
    attempt_number: int = 1

    created_at: datetime = Field(default_factory=_utcnow)


class CampaignQASummary(BaseModel):
    """Campaign-wide QA summary with brand coherence score."""

    campaign_id: str
    brand_coherence_score: float  # Weighted average of all asset scores
    total_assets: int
    approved_count: int
    failed_count: int
    escalated_count: int
    qa_results: list[QAResult]
    completed_at: datetime = Field(default_factory=_utcnow)


class AssetBundle(BaseModel):
    """The final packaged campaign output."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    brand_coherence_score: float

    # Asset inventories
    image_urls: dict[str, list[str]]  # Platform → list of GCS URLs
    video_urls: dict[str, list[str]]  # Platform → list of GCS URLs
    copy_package_id: str

    # Bundle files
    zip_gcs_url: str  # All assets as ZIP
    brand_kit_pdf_url: str  # PDF: mood board + brand specs + copy
    posting_schedule_url: str  # JSON posting calendar

    created_at: datetime = Field(default_factory=_utcnow)


# ── Distribution Pipeline Models (Phase 5) ────────────────────────────


class PostingWindow(BaseModel):
    """An optimal posting time window for a platform."""

    day_of_week: str  # "monday", "tuesday", etc.
    hour_utc: int  # 0–23
    rationale: str  # Why this time is optimal
    expected_reach_multiplier: float  # vs. average (e.g. 1.4 = 40% better)


class PostableAsset(BaseModel):
    """An asset ready for posting to a platform."""

    asset_id: str
    asset_type: str  # "image" | "video"
    platform: Platform
    gcs_url: str  # Optimized URL from Format Optimizer
    copy: PlatformCopy  # Caption, hashtags, headline


class PostScheduleItem(BaseModel):
    """A single scheduled post in the posting calendar."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    asset: PostableAsset
    scheduled_at: datetime  # UTC
    platform: Platform
    status: str = "scheduled"  # "scheduled" | "posted" | "failed" | "cancelled"
    post_url: Optional[str] = None
    cloud_scheduler_job: Optional[str] = None
    error_message: Optional[str] = None


class PostingCalendar(BaseModel):
    """A complete posting schedule for a campaign."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    items: list[PostScheduleItem]
    total_posts: int
    platforms: list[Platform]
    start_date: datetime
    end_date: datetime
    ics_gcs_url: Optional[str] = None


class AuthStatus(BaseModel):
    """OAuth authentication status for a social platform."""

    platform: Platform
    is_valid: bool
    expires_at: Optional[datetime] = None
    needs_refresh: bool
    error_message: Optional[str] = None


class PostResult(BaseModel):
    """Result of posting an asset to a social platform."""

    platform: Platform
    success: bool
    post_url: Optional[str] = None
    platform_post_id: Optional[str] = None
    posted_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_attempted: bool = False


# ── Analytics & A2A Models (Phase 6) ──────────────────────────────────


class PostMetrics(BaseModel):
    """Raw engagement metrics for a single published post."""

    post_schedule_item_id: str
    platform: Platform
    asset_id: str
    asset_type: str  # "image" | "video"

    # Reach
    impressions: int
    reach: int

    # Engagement
    likes: int
    comments: int
    shares: int
    saves: int = 0  # Instagram only

    # Video-specific
    video_views: Optional[int] = None
    video_completion_rate: Optional[float] = None  # 0.0–1.0

    # Derived
    engagement_rate: float  # (likes+comments+shares) / impressions * 100
    click_through_rate: Optional[float] = None

    # Meta
    fetched_at: datetime = Field(default_factory=_utcnow)
    hours_since_post: int  # 24, 72, or 168 (7d)


class PerformanceRanking(BaseModel):
    """Relative performance analysis across all posts in a campaign."""

    best_asset_id: str
    best_asset_type: str
    best_platform: Platform
    best_posting_hour_utc: int

    video_avg_engagement_rate: float
    image_avg_engagement_rate: float
    video_vs_image_multiplier: float  # e.g. 3.2

    platform_rankings: list[dict]  # Ordered by engagement rate
    worst_asset_id: str


class CreativeRecommendation(BaseModel):
    """Structured recommendation for next campaign iteration."""

    dimension: str  # "content_type" | "posting_time" | "platform" | "visual_style" | "copy_length"
    finding: str  # What the data showed
    recommendation: str  # What to do next time
    confidence: float  # 0.0–1.0 based on data volume
    supporting_metrics: dict  # The specific numbers


class AnalyticsInsight(BaseModel):
    """The A2A message payload sent from Analytics Agent to Orchestrator."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    brand_id: Optional[str] = None  # For brand memory (Phase 7)

    all_metrics: list[PostMetrics]
    performance_ranking: PerformanceRanking

    # Natural language
    insight_report: str  # 3-5 paragraph summary

    # Structured recommendations for agent consumption
    creative_recommendations: list[CreativeRecommendation]

    # Summary flags for Brand Memory
    bias_toward_video: bool
    top_platform: Platform
    optimal_posting_hour_utc: int

    analysis_timestamp: datetime = Field(default_factory=_utcnow)
    data_completeness: float  # 0.0–1.0 (how many platforms had data)


# ── Advanced Intelligence Models (Phase 7) ────────────────────────────


class TrendSignal(BaseModel):
    """A single real-time cultural or platform trend."""

    title: str  # e.g. "De-influencing aesthetic on TikTok"
    platform: Optional[Platform] = None  # Null if cross-platform
    category: str  # "format" | "aesthetic" | "hook" | "cultural"
    description: str
    why_relevant: str  # Why this matters for this brand
    source_url: str  # Grounding evidence
    recency: str  # e.g. "trending this week"
    confidence: float  # 0.0–1.0 (based on search result quality)


class TrendBrief(BaseModel):
    """Compiled trend research injected into Brand Strategist context."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    signals: list[TrendSignal]  # Max 8 signals
    platform_format_recommendations: dict[str, str]  # Platform → recommended format
    hook_patterns: list[str]  # 3-5 proven opening hooks for this audience
    cultural_context: str  # Paragraph on current cultural mood
    search_queries_used: list[str]  # Transparency / grounding proof
    generated_at: datetime = Field(default_factory=_utcnow)


class CompetitorProfile(BaseModel):
    """Structured analysis of a single competitor brand."""

    competitor_url: Optional[str] = None
    screenshot_gcs_url: Optional[str] = None
    brand_name: str  # Extracted from page or filename

    # Visual analysis
    dominant_colors: list[str]  # Hex values
    visual_style: str  # e.g. "clean minimalism", "maximalist luxury"
    photography_style: str  # e.g. "lifestyle", "product-only", "UGC"

    # Messaging analysis
    tone: str
    key_messages: list[str]
    target_audience_guess: str

    # Positioning
    mainstream_niche_score: float  # 0=mainstream, 1=niche
    premium_accessible_score: float  # 0=accessible, 1=premium

    # Differentiation
    weakness: str  # Their brand's weakness
    differentiation_opportunity: str  # How user's brand should position away


class CompetitorMap(BaseModel):
    """Competitive analysis map with positioning chart."""

    id: str = Field(default_factory=_uuid)
    campaign_id: str
    competitors: list[CompetitorProfile]
    user_brand_positioning: dict  # Where BrandForge places the user's brand
    differentiation_strategy: str  # Paragraph on how to stand out
    positioning_map_svg: str  # SVG string of 2x2 quadrant chart


class CampaignPerformanceSummary(BaseModel):
    """Appended to brand memory after each campaign analytics run."""

    campaign_id: str
    completed_at: datetime = Field(default_factory=_utcnow)
    brand_coherence_score: float
    top_performing_asset_type: str  # "video" | "image"
    top_performing_platform: Platform
    top_performing_tone: str
    winning_color_palette: ColorPalette
    audience_response_patterns: list[str]  # e.g. "responds to vulnerability"
    recommendations_applied: list[str]  # What was changed based on prior insights


class BrandMemory(BaseModel):
    """Persistent brand intelligence stored at /brands/{brand_id}."""

    id: str = Field(default_factory=_uuid)
    brand_name: str
    created_at: datetime = Field(default_factory=_utcnow)

    # Accumulated intelligence
    campaign_history: list[CampaignPerformanceSummary] = []  # Append-only
    campaign_count: int = 0

    # Evolved brand state
    current_brand_dna_id: Optional[str] = None  # Most recent approved Brand DNA
    evolved_color_palette: Optional[ColorPalette] = None
    content_type_bias: dict = Field(default_factory=lambda: {"video": 0.5, "image": 0.5})
    platform_priority: list[Platform] = []  # Ordered by performance
    avg_brand_coherence_score: float = 0.0  # Rolling average

    # Recommendations for next campaign
    next_campaign_recommendations: list[CreativeRecommendation] = []

    updated_at: datetime = Field(default_factory=_utcnow)


class VoiceFeedbackResult(BaseModel):
    """Result of processing user voice input by Sage."""

    transcription: str
    intent: str  # "modification" | "question" | "confirmation"
    target_agent: Optional[str] = None  # Which agent receives the modification
    instruction: Optional[str] = None  # The modification instruction
    sage_response_text: str  # Sage's reply
    sage_response_audio_url: str  # GCS URL of TTS audio
