"""Tests for the Brand QA Inspector Agent — Phase 3 Definition of Done.

8 DoD tests covering multimodal review, scoring, violations,
regeneration, frame extraction, and brand coherence.
"""

import json
import re
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import (
    BrandDNA,
    CampaignQASummary,
    CopyPackage,
    GeneratedImage,
    GeneratedVideo,
    ImageSpec,
    Platform,
    PlatformCopy,
    QAResult,
    QAViolation,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def qa_brand_dna(sample_brand_dna):
    """Return brand DNA dict for QA state."""
    return sample_brand_dna.model_dump(mode="json")


@pytest.fixture
def mock_tool_context(qa_brand_dna):
    """Return a mock ToolContext with brand DNA and assets loaded."""
    ctx = MagicMock()
    state = {
        "brand_dna": qa_brand_dna,
        "generated_images_data": [
            GeneratedImage(
                id="img-001",
                campaign_id="test-campaign-001",
                platform=Platform.INSTAGRAM,
                spec=ImageSpec(
                    platform=Platform.INSTAGRAM,
                    width=1080, height=1080,
                    aspect_ratio="1:1", use_case="feed_post",
                ),
                gcs_url="gs://brandforge-assets/campaigns/test-campaign-001/production/images/instagram_feed_post_v1.png",
                variant_number=1,
                generation_prompt="test prompt",
                brand_dna_version=1,
            ).model_dump(mode="json"),
        ],
        "generated_videos_data": [
            GeneratedVideo(
                id="vid-001",
                campaign_id="test-campaign-001",
                script_id="script-001",
                platform=Platform.INSTAGRAM,
                duration_seconds=30,
                aspect_ratio="9:16",
                gcs_url_raw="gs://brandforge-assets/campaigns/test-campaign-001/production/videos/raw.mp4",
                gcs_url_final="gs://brandforge-assets/campaigns/test-campaign-001/production/videos/final.mp4",
                operation_id="op-001",
                generation_status="complete",
            ).model_dump(mode="json"),
        ],
        "copy_package_data": CopyPackage(
            campaign_id="test-campaign-001",
            platform_copies=[
                PlatformCopy(
                    platform=Platform.INSTAGRAM,
                    caption="TestBrand makes sustainability beautiful.",
                    headline="Everyday Sustainability",
                    hashtags=["#TestBrand", "#Sustainable"],
                    cta_text="Shop Now",
                    character_count=45,
                    brand_voice_score=0.9,
                ),
            ],
            global_tagline="Sustainability without compromise.",
            press_blurb="TestBrand is redefining everyday sustainability.",
        ).model_dump(mode="json"),
        "qa_results": [],
        "qa_attempts": {},
    }
    ctx.state = state
    return ctx


# ── DoD 1: test_image_reviewed_multimodally ──────────────────────────


@pytest.mark.llm
@pytest.mark.gcp
async def test_image_reviewed_multimodally(mock_tool_context):
    """Agent calls Gemini Vision with actual image bytes, not just filename metadata."""
    from brandforge.agents.qa_inspector.tools import review_image_asset

    # Mock GCS download to return real image bytes (1x1 PNG)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    gemini_response = MagicMock()
    gemini_response.text = json.dumps({
        "overall_score": 0.85,
        "color_compliance": 0.9,
        "tone_compliance": 0.8,
        "visual_energy_compliance": 0.85,
        "violations": [],
        "approver_notes": "Image is on-brand.",
    })

    with (
        patch("brandforge.agents.qa_inspector.tools.download_blob", return_value=png_bytes) as mock_dl,
        patch("brandforge.agents.qa_inspector.tools._get_genai_client") as mock_client_fn,
    ):
        client = MagicMock()
        mock_client_fn.return_value = client
        client.models.generate_content.return_value = gemini_response

        result = await review_image_asset("test-campaign-001", "img-001", mock_tool_context)

    # Verify GCS download was called (actual bytes, not just metadata)
    mock_dl.assert_called_once()

    # Verify Gemini was called with multimodal content (image bytes + text)
    call_args = client.models.generate_content.call_args
    contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
    assert len(contents) == 2  # image part + text part
    assert result["overall_score"] == 0.85
    assert result["status"] == "approved"


# ── DoD 2: test_score_structure_valid ────────────────────────────────


def test_score_structure_valid():
    """All QAResult objects pass Pydantic validation with scores in [0.0, 1.0]."""
    result = QAResult(
        campaign_id="camp-001",
        asset_id="asset-001",
        asset_type="image",
        overall_score=0.85,
        color_compliance=0.9,
        tone_compliance=0.8,
        visual_energy_compliance=0.85,
        status="approved",
        violations=[],
        approver_notes="Good quality.",
    )
    assert 0.0 <= result.overall_score <= 1.0
    assert 0.0 <= result.color_compliance <= 1.0
    assert 0.0 <= result.tone_compliance <= 1.0
    assert 0.0 <= result.visual_energy_compliance <= 1.0
    assert result.status in ("approved", "failed", "escalated")

    # Verify round-trip serialization
    data = result.model_dump(mode="json")
    restored = QAResult.model_validate(data)
    assert restored.overall_score == result.overall_score


# ── DoD 3: test_violation_is_specific ────────────────────────────────


def test_violation_is_specific():
    """Every QAViolation.description contains at least one specific value."""
    v1 = QAViolation(
        category="color",
        severity="critical",
        description="dominant color #3B82F6 (blue) violates brand palette — expected warm earth tones (#C4894F, #2D3A2E)",
        location="full image",
        expected="#C4894F warm earth tones",
        found="#3B82F6 blue",
    )
    # Check description contains hex codes
    assert re.search(r"#[0-9A-Fa-f]{6}", v1.description)

    v2 = QAViolation(
        category="forbidden_word",
        severity="moderate",
        description="Caption uses forbidden word 'game-changer' in line 3",
        location="caption",
        expected="Avoid game-changer per brand guidelines",
        found="game-changer",
    )
    # Check description contains the specific word
    assert "game-changer" in v2.description

    v3 = QAViolation(
        category="visual_energy",
        severity="minor",
        description="Frame at 0:15 shows chaotic imagery inconsistent with minimalist direction",
        location="0:12-0:18",
        expected="minimalist visual energy",
        found="chaotic busy composition",
    )
    # Check description contains a timestamp
    assert re.search(r"\d+:\d+", v3.description)


# ── DoD 4: test_failing_asset_triggers_regeneration ──────────────────


@pytest.mark.llm
@pytest.mark.gcp
async def test_failing_asset_triggers_regeneration(mock_tool_context):
    """When overall_score < 0.80, trigger_regeneration flags the asset."""
    from brandforge.agents.qa_inspector.tools import trigger_regeneration

    # Insert a failed QA result
    mock_tool_context.state["qa_results"] = [
        QAResult(
            campaign_id="test-campaign-001",
            asset_id="img-001",
            asset_type="image",
            overall_score=0.65,
            color_compliance=0.5,
            tone_compliance=0.7,
            visual_energy_compliance=0.7,
            status="failed",
            violations=[
                QAViolation(
                    category="color",
                    severity="critical",
                    description="Wrong palette #FF0000",
                    expected="#2D3A2E",
                    found="#FF0000",
                ),
            ],
            approver_notes="Off-brand colors.",
            correction_prompt="Use earth tones (#2D3A2E, #5C6B5E) instead of red.",
        ).model_dump(mode="json"),
    ]
    mock_tool_context.state["qa_attempts"] = {"img-001": 1}

    result = await trigger_regeneration("test-campaign-001", mock_tool_context)

    assert result["regeneration_count"] == 1
    assert "img-001" in result["regeneration_assets"]
    assert mock_tool_context.state["qa_attempts"]["img-001"] == 2


# ── DoD 5: test_correction_prompt_injected ───────────────────────────


@pytest.mark.llm
@pytest.mark.gcp
async def test_correction_prompt_injected(mock_tool_context):
    """After a failed QA run, session state has a non-empty correction prompt."""
    from brandforge.agents.qa_inspector.tools import generate_correction_prompt

    # Insert a failed QA result
    mock_tool_context.state["qa_results"] = [
        QAResult(
            campaign_id="test-campaign-001",
            asset_id="img-001",
            asset_type="image",
            overall_score=0.65,
            color_compliance=0.5,
            tone_compliance=0.7,
            visual_energy_compliance=0.7,
            status="failed",
            violations=[
                QAViolation(
                    category="color",
                    severity="critical",
                    description="Wrong palette #FF0000",
                    expected="#2D3A2E",
                    found="#FF0000",
                ),
            ],
            approver_notes="Off-brand.",
        ).model_dump(mode="json"),
    ]

    gemini_response = MagicMock()
    gemini_response.text = (
        "Regenerate the Instagram feed image using earth tones: "
        "primary #2D3A2E, secondary #5C6B5E, accent #A3B18A. "
        "Remove all red (#FF0000) elements."
    )

    with patch("brandforge.agents.qa_inspector.tools._get_genai_client") as mock_fn:
        client = MagicMock()
        mock_fn.return_value = client
        client.models.generate_content.return_value = gemini_response

        result = await generate_correction_prompt(
            "test-campaign-001", "img-001", mock_tool_context
        )

    assert "correction_prompt" in result
    assert len(result["correction_prompt"]) > 0
    assert mock_tool_context.state.get("qa_correction_prompt")
    assert len(mock_tool_context.state["qa_correction_prompt"]) > 0


# ── DoD 6: test_max_two_regeneration_attempts ────────────────────────


@pytest.mark.llm
@pytest.mark.gcp
async def test_max_two_regeneration_attempts(mock_tool_context):
    """After 2 failed attempts, asset status is escalated, no more regeneration."""
    from brandforge.agents.qa_inspector.tools import trigger_regeneration

    mock_tool_context.state["qa_results"] = [
        QAResult(
            campaign_id="test-campaign-001",
            asset_id="img-001",
            asset_type="image",
            overall_score=0.55,
            color_compliance=0.4,
            tone_compliance=0.6,
            visual_energy_compliance=0.6,
            status="failed",
            violations=[],
            approver_notes="Still off-brand after retry.",
            attempt_number=2,
        ).model_dump(mode="json"),
    ]
    # Already at attempt 2
    mock_tool_context.state["qa_attempts"] = {"img-001": 2}

    result = await trigger_regeneration("test-campaign-001", mock_tool_context)

    assert result["escalated_count"] == 1
    assert result["regeneration_count"] == 0
    assert "img-001" in result["escalated_assets"]

    # Verify the QA result was updated to escalated
    updated_result = mock_tool_context.state["qa_results"][0]
    assert updated_result["status"] == "escalated"


# ── DoD 7: test_video_frame_extraction ───────────────────────────────


@pytest.mark.gcp
async def test_video_frame_extraction():
    """5 JPEG frames are extracted from a video for vision analysis."""
    from brandforge.agents.qa_inspector.tools import _extract_video_frames

    # Create a minimal test video using OpenCV
    import cv2
    import numpy as np
    import tempfile
    import os

    # Generate a 30-frame test video (1 second at 30fps)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp_path, fourcc, 30.0, (64, 64))
        for i in range(30):
            # Each frame has a different shade of grey
            frame = np.full((64, 64, 3), i * 8, dtype=np.uint8)
            writer.write(frame)
        writer.release()

        with open(tmp_path, "rb") as f:
            video_bytes = f.read()

        frames = await _extract_video_frames(
            video_bytes, "test-campaign", "test-video", num_frames=5
        )

        assert len(frames) == 5
        for frame_bytes in frames:
            # Each frame should be valid JPEG (starts with FF D8)
            assert frame_bytes[:2] == b"\xff\xd8"
    finally:
        os.unlink(tmp_path)


# ── DoD 8: test_brand_coherence_score_computed ───────────────────────


@pytest.mark.llm
@pytest.mark.gcp
async def test_brand_coherence_score_computed(mock_tool_context):
    """After all assets reviewed, brand coherence score is float in [0.0, 1.0]."""
    from brandforge.agents.qa_inspector.tools import compute_brand_coherence_score

    # Populate QA results
    mock_tool_context.state["qa_results"] = [
        QAResult(
            campaign_id="test-campaign-001",
            asset_id="img-001",
            asset_type="image",
            overall_score=0.90,
            color_compliance=0.95,
            tone_compliance=0.85,
            visual_energy_compliance=0.90,
            status="approved",
            violations=[],
            approver_notes="Excellent.",
        ).model_dump(mode="json"),
        QAResult(
            campaign_id="test-campaign-001",
            asset_id="copy_instagram_cp001",
            asset_type="copy",
            overall_score=0.85,
            color_compliance=1.0,
            tone_compliance=0.80,
            visual_energy_compliance=1.0,
            messaging_compliance=0.85,
            status="approved",
            violations=[],
            approver_notes="On-brand copy.",
        ).model_dump(mode="json"),
    ]

    with patch("brandforge.agents.qa_inspector.tools.save_document", new_callable=AsyncMock):
        result = await compute_brand_coherence_score(
            "test-campaign-001", mock_tool_context
        )

    assert "brand_coherence_score" in result
    score = result["brand_coherence_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    # (0.90 + 0.85) / 2 = 0.875
    assert abs(score - 0.875) < 0.01

    # Verify stored in session state
    assert "qa_summary" in mock_tool_context.state
    summary = CampaignQASummary.model_validate(mock_tool_context.state["qa_summary"])
    assert summary.brand_coherence_score == score
