"""Shared test fixtures for BrandForge."""

import os
import uuid

# Vertex AI env vars must be set before any ADK/genai imports.
# ADK's internal genai.Client reads these to route LLM calls through Vertex AI.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "brandforge-489114")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

import pytest

from brandforge.shared.models import (
    AssetBundle,
    AudiencePersona,
    BrandBrief,
    BrandDNA,
    Campaign,
    CampaignQASummary,
    CampaignStatus,
    ColorPalette,
    CompetitorInsight,
    ImageSpec,
    MessagingPillar,
    Platform,
    QAResult,
    QAViolation,
    SceneDirection,
    Typography,
    VideoScript,
    VisualAssetAnalysis,
    VoiceConfig,
)


@pytest.fixture
def sample_brand_brief() -> BrandBrief:
    """Return a minimal valid BrandBrief for testing."""
    return BrandBrief(
        brand_name="TestBrand",
        product_description="A sustainable water bottle",
        target_audience="Eco-conscious millennials",
        campaign_goal="product launch",
        tone_keywords=["bold", "sustainable", "urban"],
        platforms=[Platform.INSTAGRAM, Platform.LINKEDIN],
    )


@pytest.fixture
def sample_campaign(sample_brand_brief: BrandBrief) -> Campaign:
    """Return a minimal valid Campaign for testing."""
    return Campaign(brand_brief=sample_brand_brief)


@pytest.fixture
def sample_color_palette() -> ColorPalette:
    """Return a valid ColorPalette for testing."""
    return ColorPalette(
        primary="#2D3A2E",
        secondary="#5C6B5E",
        accent="#A3B18A",
        background="#F5F5F0",
        text="#1A1A1A",
    )


@pytest.fixture
def sample_visual_analysis() -> VisualAssetAnalysis:
    """Return a sample VisualAssetAnalysis for testing."""
    return VisualAssetAnalysis(
        detected_colors=["#2D3A2E", "#5C6B5E", "#A3B18A", "#F5F5F0"],
        typography_style="sans-serif minimalist",
        visual_energy="minimalist",
        existing_brand_elements=["leaf logo", "green gradient background"],
        recommended_direction="Clean, nature-inspired visuals with muted earth tones.",
    )


@pytest.fixture
def sample_brand_dna(sample_color_palette: ColorPalette) -> BrandDNA:
    """Return a fully populated BrandDNA for testing."""
    return BrandDNA(
        campaign_id="test-campaign-001",
        brand_name="TestBrand",
        brand_essence="Everyday sustainability without compromise.",
        brand_personality=["bold", "sustainable", "urban", "authentic", "innovative"],
        tone_of_voice=(
            "Direct and quietly confident. Speaks like an expert friend, "
            "not a brand. Uses concrete specifics over abstract claims."
        ),
        color_palette=sample_color_palette,
        typography=Typography(
            heading_font="Canela Display",
            body_font="Neue Haas Grotesk",
            font_personality="Editorial, high-fashion, authoritative",
        ),
        primary_persona=AudiencePersona(
            name="Urban Eco-Conscious Millennial",
            age_range="25-35",
            values=["sustainability", "authenticity", "design"],
            pain_points=["Greenwashing", "Overpriced eco products"],
            content_habits=["heavy Instagram user", "watches YouTube reviews"],
        ),
        messaging_pillars=[
            MessagingPillar(
                title="Radical Authenticity",
                one_liner="Real sustainability, not performative green.",
                supporting_points=["Transparent supply chain", "B-Corp certified"],
                avoid=["greenwashing language", "vague eco claims"],
            ),
            MessagingPillar(
                title="Design-First Utility",
                one_liner="Beautiful things that work hard.",
                supporting_points=["Award-winning industrial design", "Premium materials"],
                avoid=["cheap", "disposable", "bargain"],
            ),
            MessagingPillar(
                title="Community Impact",
                one_liner="Every purchase plants a tree.",
                supporting_points=["1% for the Planet member", "Local sourcing"],
                avoid=["guilt-tripping", "doom messaging"],
            ),
        ],
        visual_direction="Clean, nature-inspired minimalism with muted earth tones and bold typography.",
        platform_strategy={
            "instagram": "Visual storytelling with product-in-nature shots and UGC.",
            "linkedin": "Thought leadership on sustainable business practices.",
        },
        do_not_use=["eco-friendly (overused)", "game-changer", "synergy"],
        source_brief_summary="Brand: TestBrand. Product: A sustainable water bottle. Goal: product launch.",
    )


@pytest.fixture
def test_campaign_id() -> str:
    """Return a unique campaign ID per test run."""
    return f"test-campaign-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def sample_video_script(sample_brand_dna: BrandDNA) -> VideoScript:
    """Return a sample 30s VideoScript for testing."""
    return VideoScript(
        campaign_id=sample_brand_dna.campaign_id,
        platform=Platform.INSTAGRAM,
        duration_seconds=30,
        aspect_ratio="9:16",
        hook="Sustainability just got a glow-up.",
        scenes=[
            SceneDirection(
                scene_number=1,
                duration_seconds=5,
                visual_description="Close-up of water bottle catching morning light on a windowsill.",
                voiceover="What if your daily carry could change the world?",
                emotion="curiosity",
            ),
            SceneDirection(
                scene_number=2,
                duration_seconds=10,
                visual_description="Person walking through a green city park, bottle in hand.",
                voiceover="TestBrand is built for people who refuse to compromise.",
                text_overlay="No Compromise.",
                emotion="confidence",
            ),
            SceneDirection(
                scene_number=3,
                duration_seconds=10,
                visual_description="Product hero shot on recycled materials backdrop.",
                voiceover="Premium design. Zero waste. Every single time.",
                emotion="aspiration",
            ),
            SceneDirection(
                scene_number=4,
                duration_seconds=5,
                visual_description="Logo animation with earth-tone gradient.",
                voiceover="TestBrand. Everyday sustainability without compromise.",
                text_overlay="Shop Now",
                emotion="resolution",
            ),
        ],
        cta="Shop the collection at testbrand.com",
        brand_dna_version=1,
    )


@pytest.fixture
def sample_image_spec() -> ImageSpec:
    """Return a sample Instagram feed ImageSpec for testing."""
    return ImageSpec(
        platform=Platform.INSTAGRAM,
        width=1080,
        height=1080,
        aspect_ratio="1:1",
        use_case="feed_post",
    )


@pytest.fixture
def sample_platform_specs() -> list[ImageSpec]:
    """Return the full set of platform image specs for testing."""
    return [
        ImageSpec(platform=Platform.INSTAGRAM, width=1080, height=1080, aspect_ratio="1:1", use_case="feed_post"),
        ImageSpec(platform=Platform.INSTAGRAM, width=1080, height=1920, aspect_ratio="9:16", use_case="story"),
        ImageSpec(platform=Platform.LINKEDIN, width=1200, height=627, aspect_ratio="16:9", use_case="banner"),
        ImageSpec(platform=Platform.TWITTER_X, width=1600, height=900, aspect_ratio="16:9", use_case="banner"),
        ImageSpec(platform=Platform.FACEBOOK, width=1080, height=1080, aspect_ratio="1:1", use_case="feed_post"),
        ImageSpec(platform=Platform.FACEBOOK, width=1200, height=630, aspect_ratio="16:9", use_case="banner"),
    ]


@pytest.fixture
def sample_voice_config() -> VoiceConfig:
    """Return a default VoiceConfig for testing."""
    return VoiceConfig()


# Marker for tests that require live GCP services
gcp = pytest.mark.gcp
requires_gcp = pytest.mark.skipif(
    True,  # Override via CLI: pytest -m gcp --override-ini="markers=gcp"
    reason="Requires live GCP services (run with: pytest -m gcp)",
)
