"""Tests for the Format Optimizer agent — Phase 5 DoD."""

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import Platform


class TestFormatOptimizer:
    """Format Optimizer Definition of Done tests."""

    @pytest.mark.gcp
    async def test_image_resize_correct_dimensions(self):
        """Instagram feed image is exactly 1080x1080 after optimization."""
        from PIL import Image

        from brandforge.agents.format_optimizer.tools import optimize_image_for_platform

        # Create a test image (800x600)
        img = Image.new("RGB", (800, 600), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        test_bytes = buf.getvalue()

        mock_ctx = MagicMock()
        mock_ctx.state = {}

        with patch("brandforge.agents.format_optimizer.tools.download_blob", return_value=test_bytes), \
             patch("brandforge.agents.format_optimizer.tools.upload_blob") as mock_upload:
            mock_upload.return_value = "gs://test-bucket/optimized/instagram/feed.jpg"

            result = await optimize_image_for_platform(
                image_gcs_url="gs://test-bucket/campaigns/test/image.jpg",
                platform="instagram",
                use_case="feed",
                campaign_id="test-campaign",
                tool_context=mock_ctx,
            )

            assert result.startswith("gs://")
            # Verify dimensions from the uploaded bytes
            uploaded_bytes = mock_upload.call_args[0][0]
            optimized_img = Image.open(io.BytesIO(uploaded_bytes))
            assert optimized_img.size == (1080, 1080)

    @pytest.mark.gcp
    async def test_video_duration_trimmed(self):
        """A 2-minute video optimized for TikTok is trimmed to 60s max."""
        from brandforge.agents.format_optimizer.tools import optimize_video_for_platform

        mock_ctx = MagicMock()
        mock_ctx.state = {}

        with patch("brandforge.agents.format_optimizer.tools.download_blob", return_value=b"fake_video"), \
             patch("brandforge.agents.format_optimizer.tools.upload_blob", return_value="gs://test/optimized.mp4"), \
             patch("brandforge.agents.format_optimizer.tools.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stderr="")

            result = await optimize_video_for_platform(
                video_gcs_url="gs://test-bucket/campaigns/test/video.mp4",
                platform="tiktok",
                use_case="video",
                campaign_id="test-campaign",
                tool_context=mock_ctx,
            )

            # Verify FFmpeg was called with -t 60
            call_args = mock_sub.run.call_args[0][0]
            t_idx = call_args.index("-t")
            assert call_args[t_idx + 1] == "60"

    async def test_file_size_within_limits(self):
        """All optimized assets are within their platform's max_size_mb."""
        from PIL import Image

        from brandforge.agents.format_optimizer.tools import optimize_image_for_platform

        # Create a large test image
        img = Image.new("RGB", (4000, 4000), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=100)
        test_bytes = buf.getvalue()

        mock_ctx = MagicMock()
        mock_ctx.state = {}

        with patch("brandforge.agents.format_optimizer.tools.download_blob", return_value=test_bytes), \
             patch("brandforge.agents.format_optimizer.tools.upload_blob") as mock_upload:
            mock_upload.return_value = "gs://test-bucket/optimized.jpg"

            result = await optimize_image_for_platform(
                image_gcs_url="gs://test-bucket/test.jpg",
                platform="linkedin",
                use_case="post",
                campaign_id="test-campaign",
                tool_context=mock_ctx,
            )

            assert result.startswith("gs://")
            uploaded_bytes = mock_upload.call_args[0][0]
            # LinkedIn post max is 5MB
            assert len(uploaded_bytes) <= 5 * 1024 * 1024
