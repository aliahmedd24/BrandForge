"""Tests for Firestore connectivity and CRUD operations.

These tests require a live Firestore instance. They will be marked
[UNVERIFIED] if GCP is not configured.
"""

from __future__ import annotations

import uuid

import pytest

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_CAMPAIGNS,
)
from brandforge.shared.firestore import (
    create_document,
    get_document,
    update_document,
)
from brandforge.shared.models import (
    BrandBrief,
    Campaign,
    CampaignStatus,
    Platform,
)


def _make_test_campaign() -> Campaign:
    """Create a minimal test campaign."""
    return Campaign(
        brand_brief=BrandBrief(
            brand_name="FirestoreTest",
            product_description="Testing Firestore connectivity",
            target_audience="CI pipeline",
            campaign_goal="integration test",
            tone_keywords=["test"],
            platforms=[Platform.INSTAGRAM],
        )
    )


@pytest.mark.asyncio
async def test_firestore_write_and_read_campaign() -> None:
    """Can write and read a Campaign document in Firestore."""
    campaign = _make_test_campaign()
    doc_data = campaign.model_dump(mode="json")

    # Write
    doc_id = await create_document(
        FIRESTORE_COLLECTION_CAMPAIGNS, campaign.id, doc_data
    )
    assert doc_id == campaign.id

    # Read
    retrieved = await get_document(FIRESTORE_COLLECTION_CAMPAIGNS, campaign.id)
    assert retrieved is not None
    assert retrieved["brand_brief"]["brand_name"] == "FirestoreTest"
    assert retrieved["status"] == CampaignStatus.PENDING.value


@pytest.mark.asyncio
async def test_firestore_update_campaign_status() -> None:
    """Can update a Campaign document's status field."""
    campaign = _make_test_campaign()
    doc_data = campaign.model_dump(mode="json")
    await create_document(FIRESTORE_COLLECTION_CAMPAIGNS, campaign.id, doc_data)

    # Update
    await update_document(
        FIRESTORE_COLLECTION_CAMPAIGNS,
        campaign.id,
        {"status": CampaignStatus.RUNNING.value},
    )

    # Verify
    updated = await get_document(FIRESTORE_COLLECTION_CAMPAIGNS, campaign.id)
    assert updated is not None
    assert updated["status"] == CampaignStatus.RUNNING.value


@pytest.mark.asyncio
async def test_firestore_get_nonexistent_returns_none() -> None:
    """Getting a document that doesn't exist should return None."""
    fake_id = f"nonexistent-{uuid.uuid4()}"
    result = await get_document(FIRESTORE_COLLECTION_CAMPAIGNS, fake_id)
    assert result is None
