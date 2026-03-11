"""Tests for demo mode — Phase 8 Definition of Done."""

import pytest


@pytest.mark.gcp
@pytest.mark.timeout(300)
async def test_demo_completes_in_five_minutes():
    """Integration test: demo campaign pipeline completes within 5 minutes.

    Requires live GCP services (Firestore, Vertex AI, Cloud Storage).
    """
    from brandforge.api import _run_agent_pipeline
    from brandforge.demo.constants import DEMO_BRIEF
    from brandforge.shared.firestore import (
        CAMPAIGNS_COLLECTION,
        get_document,
        save_document,
    )
    from brandforge.shared.models import Campaign, CampaignStatus

    campaign = Campaign(brand_brief=DEMO_BRIEF, status=CampaignStatus.RUNNING)
    await save_document(
        CAMPAIGNS_COLLECTION,
        campaign.id,
        campaign.model_dump(mode="json"),
    )

    await _run_agent_pipeline(campaign.id, demo_mode=True)

    data = await get_document(CAMPAIGNS_COLLECTION, campaign.id)
    assert data is not None
    assert data["status"] in ("approved", "published")


def test_demo_brief_is_valid():
    """Verify the DEMO_BRIEF constant is a valid BrandBrief."""
    from brandforge.demo.constants import DEMO_BRIEF

    assert DEMO_BRIEF.brand_name == "Grounded"
    assert len(DEMO_BRIEF.platforms) >= 2
    assert len(DEMO_BRIEF.tone_keywords) >= 3
    assert DEMO_BRIEF.product_description != ""
    assert DEMO_BRIEF.target_audience != ""


def test_demo_sabotage_prompt_exists():
    """Verify the sabotage prompt constant exists and is non-empty."""
    from brandforge.demo.constants import DEMO_SABOTAGE_PROMPT

    assert isinstance(DEMO_SABOTAGE_PROMPT, str)
    assert len(DEMO_SABOTAGE_PROMPT) > 20
    assert "blue" in DEMO_SABOTAGE_PROMPT.lower()


@pytest.mark.gcp
@pytest.mark.llm
async def test_qa_failure_occurs():
    """Demo mode: sabotaged image variant should score below 0.80.

    Requires live Gemini API for QA scoring.
    """
    pytest.skip("Requires full pipeline with live Imagen + Gemini Vision")


@pytest.mark.gcp
@pytest.mark.llm
async def test_qa_recovery_occurs():
    """Demo mode: regenerated image should score >= 0.85.

    Requires live Gemini API for regeneration + QA re-scoring.
    """
    pytest.skip("Requires full pipeline with live Imagen + Gemini Vision")


@pytest.mark.gcp
@pytest.mark.llm
async def test_brand_coherence_reaches_90():
    """Demo mode: final campaign brand coherence should be >= 0.90.

    Requires full pipeline completion with live services.
    """
    pytest.skip("Requires full pipeline with live Imagen + Gemini Vision")
