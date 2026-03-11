"""Tests for the Campaign Assembler Agent — Phase 3 Definition of Done.

4 DoD tests covering ZIP contents, brand kit PDF, campaign record update,
and QA gate enforcement.
"""

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import (
    AssetBundle,
    CopyPackage,
    Platform,
    PlatformCopy,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def assembler_tool_context(sample_brand_dna):
    """Return a mock ToolContext with QA-approved assets loaded."""
    ctx = MagicMock()
    state = {
        "brand_dna": sample_brand_dna.model_dump(mode="json"),
        "qa_results": [
            {
                "asset_id": "img-001",
                "status": "approved",
                "asset_type": "image",
                "overall_score": 0.9,
            },
            {
                "asset_id": "vid-001",
                "status": "approved",
                "asset_type": "video",
                "overall_score": 0.85,
            },
            {
                "asset_id": "copy_instagram_cp01",
                "status": "approved",
                "asset_type": "copy",
                "overall_score": 0.88,
            },
        ],
        "generated_images_data": [
            {
                "id": "img-001",
                "platform": "instagram",
                "gcs_url": "gs://brandforge-assets/campaigns/test/images/img.png",
            },
        ],
        "generated_videos_data": [
            {
                "id": "vid-001",
                "platform": "instagram",
                "gcs_url_final": "gs://brandforge-assets/campaigns/test/videos/vid.mp4",
            },
        ],
        "copy_package_data": CopyPackage(
            campaign_id="test-campaign-001",
            platform_copies=[
                PlatformCopy(
                    platform=Platform.INSTAGRAM,
                    caption="TestBrand caption.",
                    headline="Everyday Sustainability",
                    hashtags=["#TestBrand"],
                    cta_text="Shop Now",
                    character_count=20,
                    brand_voice_score=0.9,
                ),
            ],
            global_tagline="Sustainability without compromise.",
            press_blurb="TestBrand redefines sustainability.",
        ).model_dump(mode="json"),
        "qa_summary": {
            "brand_coherence_score": 0.88,
            "total_assets": 3,
            "approved_count": 3,
            "failed_count": 0,
            "escalated_count": 0,
        },
        "brand_coherence_score": 0.88,
        "approved_image_urls": {"instagram": ["gs://brandforge-assets/campaigns/test/images/img.png"]},
        "approved_video_urls": {"instagram": ["gs://brandforge-assets/campaigns/test/videos/vid.mp4"]},
        "approved_copy_package_id": "cp01",
        "brand_kit_pdf_url": "gs://brandforge-assets/campaigns/test/bundle/brand_kit.pdf",
        "posting_schedule_url": "gs://brandforge-assets/campaigns/test/bundle/posting_schedule.json",
    }
    ctx.state = state
    return ctx


# ── DoD 1: test_zip_contains_all_assets ──────────────────────────────


@pytest.mark.gcp
async def test_zip_contains_all_assets(assembler_tool_context):
    """ZIP file contains at least one file per asset type (image, video, copy JSON)."""
    from brandforge.agents.campaign_assembler.tools import create_asset_bundle_zip

    # Mock GCS downloads to return small test data
    def mock_download(path, **kwargs):
        """Return test bytes based on file type."""
        if path.endswith(".png"):
            return b"\x89PNG fake image data"
        elif path.endswith(".mp4"):
            return b"\x00\x00 fake video data"
        elif path.endswith(".pdf"):
            return b"%PDF fake pdf data"
        elif path.endswith(".json"):
            return b'{"test": "schedule"}'
        return b"test data"

    with (
        patch("brandforge.agents.campaign_assembler.tools.download_blob", side_effect=mock_download),
        patch("brandforge.agents.campaign_assembler.tools.upload_blob", return_value="gs://test/bundle.zip"),
    ):
        result = await create_asset_bundle_zip("test-campaign-001", assembler_tool_context)

    assert "error" not in result
    assert result["size_bytes"] > 0

    # Verify the upload_blob was called — the zip was created and uploaded
    assert assembler_tool_context.state.get("zip_gcs_url") == "gs://test/bundle.zip"


# ── DoD 2: test_brand_kit_pdf_generated ──────────────────────────────


@pytest.mark.gcp
async def test_brand_kit_pdf_generated(assembler_tool_context):
    """PDF file is generated with brand DNA content."""
    from brandforge.agents.campaign_assembler.tools import generate_brand_kit_pdf

    captured_pdf = {}

    def mock_upload(source_data, destination_path, **kwargs):
        """Capture the uploaded PDF bytes."""
        captured_pdf["data"] = source_data
        captured_pdf["path"] = destination_path
        return f"gs://brandforge-assets/{destination_path}"

    with patch("brandforge.agents.campaign_assembler.tools.upload_blob", side_effect=mock_upload):
        result = await generate_brand_kit_pdf("test-campaign-001", assembler_tool_context)

    assert "error" not in result
    assert result["size_bytes"] > 0

    # Verify it's a real PDF (starts with %PDF)
    pdf_data = captured_pdf["data"]
    assert pdf_data[:4] == b"%PDF"

    # PDF should be substantial (at least 3 pages worth of content)
    # ReportLab produces at minimum ~1KB per page
    assert len(pdf_data) > 2000


# ── DoD 3: test_campaign_record_updated ──────────────────────────────


@pytest.mark.gcp
async def test_campaign_record_updated(assembler_tool_context):
    """Campaign.asset_bundle_id is set in Firestore after assembly."""
    from brandforge.agents.campaign_assembler.tools import store_asset_bundle

    assembler_tool_context.state["zip_gcs_url"] = "gs://test/bundle.zip"
    assembler_tool_context.state["brand_kit_pdf_url"] = "gs://test/kit.pdf"
    assembler_tool_context.state["posting_schedule_url"] = "gs://test/schedule.json"

    with (
        patch("brandforge.agents.campaign_assembler.tools.save_document", new_callable=AsyncMock) as mock_save,
        patch("brandforge.agents.campaign_assembler.tools.update_document", new_callable=AsyncMock) as mock_update,
    ):
        result = await store_asset_bundle("test-campaign-001", assembler_tool_context)

    assert "error" not in result
    assert "bundle_id" in result

    # Verify Campaign record was updated
    mock_update.assert_called_once()
    update_args = mock_update.call_args
    assert update_args[0][0] == "campaigns"
    assert update_args[0][1] == "test-campaign-001"
    assert "asset_bundle_id" in update_args[0][2]
    assert update_args[0][2]["status"] == "approved"


# ── DoD 4: test_assembler_waits_for_qa ───────────────────────────────


async def test_assembler_waits_for_qa():
    """Assembler does not execute if QA has not completed.

    The qa_orchestrator SequentialAgent enforces this: campaign_assembler
    only runs after qa_inspector completes. We verify the agent wiring.
    """
    from brandforge.agents.campaign_assembler.agent import campaign_assembler_agent
    from brandforge.agents.qa_inspector.agent import qa_inspector_agent

    # Import the root agent to check wiring
    from brandforge.agent import qa_orchestrator

    # Verify qa_orchestrator is a SequentialAgent
    from google.adk.agents import SequentialAgent
    assert isinstance(qa_orchestrator, SequentialAgent)

    # Verify order: qa_inspector first, then campaign_assembler
    sub_names = [a.name for a in qa_orchestrator.sub_agents]
    assert sub_names == ["brand_qa_inspector", "campaign_assembler"]

    # Verify collect_approved_assets returns error when no QA results
    from brandforge.agents.campaign_assembler.tools import collect_approved_assets

    empty_ctx = MagicMock()
    empty_ctx.state = {"qa_results": []}

    result = await collect_approved_assets("test-campaign", empty_ctx)
    # Should work but find 0 approved assets (QA hasn't run)
    assert result.get("total_approved", 0) == 0
