"""Tests for the Brand Memory Agent — Phase 7 Definition of Done.

Covers: first campaign creates brand, history is append-only,
intake form pre-populated, and content bias computed.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import (
    BrandMemory,
    CampaignPerformanceSummary,
    ColorPalette,
    CreativeRecommendation,
    Platform,
)

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def sample_color_palette():
    """Return a valid ColorPalette."""
    return ColorPalette(
        primary="#2D3A2E", secondary="#4A5D4B",
        accent="#D4A574", background="#F5F0EB", text="#1A1A1A",
    )


@pytest.fixture
def sample_performance_summary(sample_color_palette):
    """Return a valid CampaignPerformanceSummary."""
    return CampaignPerformanceSummary(
        campaign_id="campaign-001",
        brand_coherence_score=0.87,
        top_performing_asset_type="video",
        top_performing_platform=Platform.INSTAGRAM,
        top_performing_tone="warm and authentic",
        winning_color_palette=sample_color_palette,
        audience_response_patterns=["responds to vulnerability"],
        recommendations_applied=[],
    )


@pytest.fixture
def sample_brand_memory(sample_performance_summary):
    """Return a BrandMemory with 1 campaign."""
    return BrandMemory(
        brand_name="TestBrand",
        campaign_history=[sample_performance_summary],
        campaign_count=1,
        current_brand_dna_id="dna-001",
        content_type_bias={"video": 0.6, "image": 0.4},
        platform_priority=[Platform.INSTAGRAM],
        avg_brand_coherence_score=0.87,
        next_campaign_recommendations=[
            CreativeRecommendation(
                dimension="content_type",
                finding="Video outperformed images by 2.3x",
                recommendation="Increase video content ratio to 70%",
                confidence=0.85,
                supporting_metrics={"video_engagement": 4.5, "image_engagement": 1.9},
            ),
        ],
    )


# ── DoD Test: First campaign creates brand ─────────────────────────────


@pytest.mark.asyncio
async def test_first_campaign_creates_brand():
    """A Brand document should be created in Firestore on first campaign."""
    from brandforge.agents.brand_memory.tools import update_brand_memory

    mock_context = MagicMock()
    mock_context.state = {
        "campaign_id": "campaign-001",
        "brand_dna": {
            "color_palette": {
                "primary": "#2D3A2E", "secondary": "#4A5D4B",
                "accent": "#D4A574", "background": "#F5F0EB", "text": "#1A1A1A",
            },
        },
        "brand_memory": {},  # No existing memory
    }

    saved_docs = []

    async def mock_save(collection, doc_id, data):
        """Capture saved documents."""
        saved_docs.append({"collection": collection, "doc_id": doc_id, "data": data})

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "content_type_bias": {"video": 0.6, "image": 0.4},
        "platform_priority": ["instagram"],
        "recommendations": [],
    })
    mock_client.models.generate_content.return_value = mock_response

    with patch(
        "brandforge.agents.brand_memory.tools._get_genai_client",
        return_value=mock_client,
    ), patch(
        "brandforge.agents.brand_memory.tools.save_document",
        side_effect=mock_save,
    ):
        result = await update_brand_memory(
            brand_name="NewBrand",
            campaign_id="campaign-001",
            brand_coherence_score=0.82,
            top_performing_asset_type="video",
            top_performing_platform="instagram",
            top_performing_tone="authentic",
            brand_dna_id="dna-001",
            tool_context=mock_context,
        )

    assert result
    assert result["brand_name"] == "NewBrand"
    assert result["campaign_count"] == 1
    assert len(saved_docs) == 1
    assert saved_docs[0]["collection"] == "brands"


# ── DoD Test: History is append-only ───────────────────────────────────


@pytest.mark.asyncio
async def test_history_is_append_only(sample_brand_memory, sample_color_palette):
    """After 3 campaigns, brand.campaign_history must have exactly 3 entries."""
    from brandforge.agents.brand_memory.tools import update_brand_memory

    memory = sample_brand_memory.model_copy()
    # Add 2nd campaign
    memory.campaign_history.append(
        CampaignPerformanceSummary(
            campaign_id="campaign-002",
            brand_coherence_score=0.91,
            top_performing_asset_type="image",
            top_performing_platform=Platform.TIKTOK,
            top_performing_tone="playful",
            winning_color_palette=sample_color_palette,
            audience_response_patterns=[],
            recommendations_applied=[],
        )
    )
    memory.campaign_count = 2

    mock_context = MagicMock()
    mock_context.state = {
        "campaign_id": "campaign-003",
        "brand_memory": memory.model_dump(mode="json"),
        "brand_memory_id": memory.id,
        "brand_dna": {
            "color_palette": sample_color_palette.model_dump(mode="json"),
        },
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "content_type_bias": {"video": 0.5, "image": 0.5},
        "platform_priority": ["instagram", "tiktok"],
        "recommendations": [],
    })
    mock_client.models.generate_content.return_value = mock_response

    with patch(
        "brandforge.agents.brand_memory.tools._get_genai_client",
        return_value=mock_client,
    ), patch(
        "brandforge.agents.brand_memory.tools.save_document",
        new_callable=AsyncMock,
    ):
        result = await update_brand_memory(
            brand_name="TestBrand",
            campaign_id="campaign-003",
            brand_coherence_score=0.88,
            top_performing_asset_type="video",
            top_performing_platform="instagram",
            top_performing_tone="warm",
            brand_dna_id="dna-003",
            tool_context=mock_context,
        )

    assert result["campaign_count"] == 3
    assert len(result["campaign_history"]) == 3
    # Verify campaign IDs are distinct (append, not overwrite)
    campaign_ids = [c["campaign_id"] for c in result["campaign_history"]]
    assert campaign_ids == ["campaign-001", "campaign-002", "campaign-003"]


# ── DoD Test: Intake form pre-populated ────────────────────────────────


@pytest.mark.asyncio
async def test_intake_form_pre_populated(sample_brand_memory):
    """On second campaign, API should return next_campaign_recommendations."""
    from brandforge.agents.brand_memory.tools import apply_memory_recommendations

    mock_context = MagicMock()
    mock_context.state = {
        "campaign_id": "campaign-002",
        "brand_memory": sample_brand_memory.model_dump(mode="json"),
    }

    result = await apply_memory_recommendations(
        campaign_id="campaign-002",
        tool_context=mock_context,
    )

    assert result["applied"] is True
    assert result["campaign_count"] == 1
    assert len(result["recommendations"]) > 0
    assert "content_type_bias" in result
    assert "memory_recommendations" in mock_context.state


@pytest.mark.asyncio
async def test_first_run_no_pre_population():
    """First-run brand (no memory) should return applied=False."""
    from brandforge.agents.brand_memory.tools import apply_memory_recommendations

    mock_context = MagicMock()
    mock_context.state = {
        "campaign_id": "campaign-001",
        "brand_memory": {},
    }

    result = await apply_memory_recommendations(
        campaign_id="campaign-001",
        tool_context=mock_context,
    )

    assert result["applied"] is False
    assert result["reason"] == "first_campaign"


# ── DoD Test: Content bias computed ────────────────────────────────────


@pytest.mark.asyncio
async def test_content_bias_computed():
    """After 1 campaign with video outperforming, content_type_bias.video > 0.5."""
    from brandforge.agents.brand_memory.tools import update_brand_memory

    mock_context = MagicMock()
    mock_context.state = {
        "campaign_id": "campaign-001",
        "brand_memory": {},
        "brand_dna": {
            "color_palette": {
                "primary": "#1A1A2E", "secondary": "#16213E",
                "accent": "#0F3460", "background": "#F5F5F5", "text": "#1A1A1A",
            },
        },
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "content_type_bias": {"video": 0.7, "image": 0.3},
        "platform_priority": ["tiktok", "instagram"],
        "recommendations": [
            {
                "dimension": "content_type",
                "finding": "Video had 3x engagement",
                "recommendation": "Prioritize video",
                "confidence": 0.9,
                "supporting_metrics": {},
            },
        ],
    })
    mock_client.models.generate_content.return_value = mock_response

    with patch(
        "brandforge.agents.brand_memory.tools._get_genai_client",
        return_value=mock_client,
    ), patch(
        "brandforge.agents.brand_memory.tools.save_document",
        new_callable=AsyncMock,
    ):
        result = await update_brand_memory(
            brand_name="VideoBrand",
            campaign_id="campaign-001",
            brand_coherence_score=0.85,
            top_performing_asset_type="video",
            top_performing_platform="tiktok",
            top_performing_tone="energetic",
            brand_dna_id="dna-001",
            tool_context=mock_context,
        )

    assert result["content_type_bias"]["video"] > 0.5
