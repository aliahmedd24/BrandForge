"""Tests for Firestore client helpers.

Tests marked with @pytest.mark.gcp require live GCP Firestore access.
Run with: pytest -m gcp
"""

import pytest

from brandforge.shared.firestore import (
    CAMPAIGNS_COLLECTION,
    get_document,
    save_document,
    update_document,
)
from brandforge.shared.models import Campaign, CampaignStatus


@pytest.mark.gcp
class TestFirestoreOperations:
    """Integration tests for Firestore read/write operations."""

    @pytest.mark.asyncio
    async def test_save_and_get_campaign(self, sample_campaign: Campaign) -> None:
        """Write a Campaign doc and read it back."""
        data = sample_campaign.model_dump(mode="json")
        await save_document(CAMPAIGNS_COLLECTION, sample_campaign.id, data)

        result = await get_document(CAMPAIGNS_COLLECTION, sample_campaign.id)
        assert result is not None
        assert result["brand_brief"]["brand_name"] == "TestBrand"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_update_campaign_status(self, sample_campaign: Campaign) -> None:
        """Update a Campaign's status field."""
        data = sample_campaign.model_dump(mode="json")
        await save_document(CAMPAIGNS_COLLECTION, sample_campaign.id, data)

        await update_document(
            CAMPAIGNS_COLLECTION,
            sample_campaign.id,
            {"status": CampaignStatus.RUNNING.value},
        )

        result = await get_document(CAMPAIGNS_COLLECTION, sample_campaign.id)
        assert result is not None
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_nonexistent_document(self) -> None:
        """Getting a non-existent document returns None."""
        result = await get_document(CAMPAIGNS_COLLECTION, "does-not-exist-xyz")
        assert result is None
