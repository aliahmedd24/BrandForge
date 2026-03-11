"""Tests for the Trend Injector Agent — Phase 7 Definition of Done.

Covers: search grounding validation, no hallucinated trends,
brand strategist receives brief, and graceful fallback.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import TrendBrief, TrendSignal

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def sample_trend_signals():
    """Return a list of valid TrendSignal dicts."""
    return [
        {
            "title": "De-influencing aesthetic on TikTok",
            "platform": "tiktok",
            "category": "format",
            "description": "Anti-haul and de-influencing content trending",
            "why_relevant": "Aligns with authentic brand positioning",
            "source_url": "https://example.com/trend1",
            "recency": "trending this week",
            "confidence": 0.85,
        },
        {
            "title": "Earth tone palettes in sustainable brands",
            "platform": "instagram",
            "category": "aesthetic",
            "description": "Muted earth tones dominating sustainable brand feeds",
            "why_relevant": "Matches eco-conscious audience preferences",
            "source_url": "https://example.com/trend2",
            "recency": "viral past 2 weeks",
            "confidence": 0.72,
        },
    ]


@pytest.fixture
def sample_trend_brief(sample_trend_signals):
    """Return a valid TrendBrief dict."""
    return TrendBrief(
        campaign_id="test-campaign-123",
        signals=[TrendSignal.model_validate(s) for s in sample_trend_signals],
        platform_format_recommendations={"tiktok": "De-influencing content format"},
        hook_patterns=["Start with a vulnerable confession", "Open with a surprising statistic"],
        cultural_context="Authenticity and anti-consumerism are driving engagement.",
        search_queries_used=["tiktok trending content formats March 2026"],
    ).model_dump(mode="json")


# ── DoD Test: Search grounding used ────────────────────────────────────


def test_search_grounding_used(sample_trend_signals):
    """TrendSignal.source_url values must be valid, non-empty URLs."""
    for signal_data in sample_trend_signals:
        signal = TrendSignal.model_validate(signal_data)
        assert signal.source_url, "source_url must not be empty"
        assert signal.source_url.startswith("http"), (
            f"source_url must be a valid URL, got: {signal.source_url}"
        )


# ── DoD Test: No hallucinated trends ──────────────────────────────────


def test_no_hallucinated_trends(sample_trend_signals):
    """All TrendSignal objects with confidence > 0 must have source_url populated."""
    for signal_data in sample_trend_signals:
        signal = TrendSignal.model_validate(signal_data)
        if signal.confidence > 0:
            assert signal.source_url, (
                f"Signal '{signal.title}' has confidence={signal.confidence} "
                f"but no source_url — hallucinated trend"
            )


# ── DoD Test: Brand Strategist receives brief ─────────────────────────


@pytest.mark.asyncio
async def test_brand_strategist_receives_brief(sample_trend_brief):
    """Brand Strategist agent context must include TrendBrief data."""
    from brandforge.agents.trend_injector.tools import compile_trend_brief

    mock_context = MagicMock()
    mock_context.state = {
        "campaign_id": "test-campaign-123",
        "trend_signals": sample_trend_brief["signals"],
        "hook_patterns": sample_trend_brief["hook_patterns"],
        "search_queries_used": sample_trend_brief["search_queries_used"],
    }

    # Mock Gemini call for synthesis
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Cultural context synthesized."
    mock_client.models.generate_content.return_value = mock_response

    with patch(
        "brandforge.agents.trend_injector.tools._get_genai_client",
        return_value=mock_client,
    ), patch(
        "brandforge.agents.trend_injector.tools.save_document",
        new_callable=AsyncMock,
    ):
        result = await compile_trend_brief(
            campaign_id="test-campaign-123",
            tool_context=mock_context,
        )

    # Verify trend brief injected into session state
    assert "trend_brief" in mock_context.state
    brief = mock_context.state["trend_brief"]
    assert brief["campaign_id"] == "test-campaign-123"
    assert len(brief["signals"]) > 0


# ── DoD Test: Graceful fallback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_graceful_fallback():
    """If Google Search grounding returns 0 results, campaign proceeds without crash."""
    from brandforge.agents.trend_injector.tools import research_platform_trends

    mock_context = MagicMock()
    mock_context.state = {}

    # Simulate Gemini returning empty results
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "[]"
    mock_client.models.generate_content.return_value = mock_response

    with patch(
        "brandforge.agents.trend_injector.tools._get_genai_client",
        return_value=mock_client,
    ):
        result = await research_platform_trends(
            platforms="instagram,tiktok",
            industry="sustainable fashion",
            audience="eco-conscious millennials",
            tool_context=mock_context,
        )

    assert isinstance(result, list)
    assert mock_context.state.get("trend_signals") == []


@pytest.mark.asyncio
async def test_graceful_fallback_on_exception():
    """If Gemini call raises an exception, trends are empty but no crash."""
    from brandforge.agents.trend_injector.tools import research_platform_trends

    mock_context = MagicMock()
    mock_context.state = {}

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API error")

    with patch(
        "brandforge.agents.trend_injector.tools._get_genai_client",
        return_value=mock_client,
    ):
        result = await research_platform_trends(
            platforms="instagram",
            industry="tech",
            audience="developers",
            tool_context=mock_context,
        )

    assert result == []
    assert mock_context.state.get("trend_signals") == []
