"""Shared test fixtures for BrandForge."""

import pytest

from brandforge.shared.models import (
    AudiencePersona,
    BrandBrief,
    BrandDNA,
    Campaign,
    CampaignStatus,
    ColorPalette,
    CompetitorInsight,
    MessagingPillar,
    Platform,
    Typography,
    VisualAssetAnalysis,
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


# Marker for tests that require live GCP services
gcp = pytest.mark.gcp
requires_gcp = pytest.mark.skipif(
    True,  # Override via CLI: pytest -m gcp --override-ini="markers=gcp"
    reason="Requires live GCP services (run with: pytest -m gcp)",
)
