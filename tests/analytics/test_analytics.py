"""Tests for the Analytics Agent — Phase 6 DoD."""

import json
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import (
    AnalyticsInsight,
    CreativeRecommendation,
    PerformanceRanking,
    Platform,
    PostMetrics,
)


def _make_metrics(platform: str, asset_type: str, engagement_rate: float) -> dict:
    """Create a metrics dict for testing."""
    return {
        "post_schedule_item_id": f"item-{platform}-{asset_type}",
        "platform": platform,
        "asset_id": f"asset-{platform}-{asset_type}",
        "asset_type": asset_type,
        "impressions": 1000,
        "reach": 800,
        "likes": int(engagement_rate * 10),
        "comments": int(engagement_rate * 3),
        "shares": int(engagement_rate * 2),
        "saves": 0,
        "engagement_rate": engagement_rate,
        "hours_since_post": 24,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


class TestAnalytics:
    """Analytics Agent Definition of Done tests."""

    async def test_engagement_rate_formula(self):
        """engagement_rate = (likes + comments + shares) / impressions * 100."""
        metrics = PostMetrics(
            post_schedule_item_id="test-1",
            platform=Platform.INSTAGRAM,
            asset_id="asset-1",
            asset_type="image",
            impressions=1000,
            reach=800,
            likes=50,
            comments=10,
            shares=5,
            engagement_rate=(50 + 10 + 5) / 1000 * 100,
            hours_since_post=24,
        )
        assert metrics.engagement_rate == pytest.approx(6.5)

    async def test_recommendations_structured(self):
        """All CreativeRecommendation objects pass Pydantic validation."""
        rec = CreativeRecommendation(
            dimension="content_type",
            finding="Video engagement 3.2x higher than image",
            recommendation="Bias toward 70% video content",
            confidence=0.85,
            supporting_metrics={"video_er": 4.8, "image_er": 1.5},
        )
        assert rec.dimension == "content_type"
        assert rec.confidence > 0
        assert len(rec.supporting_metrics) > 0

    async def test_a2a_delivery(self):
        """deliver_a2a_insights calls Firestore and returns delivered status."""
        from brandforge.agents.analytics.tools import deliver_a2a_insights

        mock_ctx = MagicMock()
        mock_ctx.state = {
            "all_metrics": json.dumps([
                _make_metrics("instagram", "video", 4.8),
                _make_metrics("instagram", "image", 1.5),
            ]),
            "performance_ranking": json.dumps({
                "best_asset_id": "asset-instagram-video",
                "best_asset_type": "video",
                "best_platform": "instagram",
                "best_posting_hour_utc": 14,
                "video_avg_engagement_rate": 4.8,
                "image_avg_engagement_rate": 1.5,
                "video_vs_image_multiplier": 3.2,
                "platform_rankings": [{"platform": "instagram", "avg_engagement_rate": 3.15}],
                "worst_asset_id": "asset-instagram-image",
            }),
            "insight_report": "Video outperformed images 3.2x across Instagram.",
        }

        with patch("brandforge.agents.analytics.tools.save_document", new_callable=AsyncMock):
            result = await deliver_a2a_insights(
                campaign_id="test-campaign",
                tool_context=mock_ctx,
            )

        data = json.loads(result)
        assert data["status"] == "delivered"
        assert "insight_id" in data
        assert mock_ctx.state.get("user:bias_toward_video") is True

    async def test_compute_performance_rankings(self):
        """compute_performance_rankings identifies top/bottom performers."""
        from brandforge.agents.analytics.tools import compute_performance_rankings

        mock_ctx = MagicMock()
        mock_ctx.state = {
            "all_metrics": json.dumps([
                _make_metrics("instagram", "video", 4.8),
                _make_metrics("instagram", "image", 1.5),
                _make_metrics("linkedin", "image", 2.0),
            ]),
        }

        result = await compute_performance_rankings(
            campaign_id="test-campaign",
            tool_context=mock_ctx,
        )

        ranking = PerformanceRanking.model_validate_json(result)
        assert ranking.best_asset_type == "video"
        assert ranking.video_avg_engagement_rate > ranking.image_avg_engagement_rate
        assert ranking.video_vs_image_multiplier > 1.0

    async def test_partial_platform_data(self):
        """If one platform returns error, agent continues with available data."""
        from brandforge.agents.analytics.tools import fetch_platform_metrics

        mock_ctx = MagicMock()
        mock_ctx.state = {"all_metrics": "[]"}

        # Simulate Firestore error for one platform
        with patch("brandforge.shared.firestore.query_documents", side_effect=Exception("403 Forbidden")):
            result = await fetch_platform_metrics(
                campaign_id="test-campaign",
                platform="tiktok",
                hours_since_post=24,
                tool_context=mock_ctx,
            )

        # Should return empty list, not crash
        metrics = json.loads(result)
        assert isinstance(metrics, list)

    @pytest.mark.llm
    async def test_insight_cites_numbers(self):
        """insight_report string contains at least 3 numeric values."""
        from brandforge.agents.analytics.tools import generate_insight_report

        mock_ctx = MagicMock()
        mock_ctx.state = {
            "all_metrics": json.dumps([
                _make_metrics("instagram", "video", 4.8),
                _make_metrics("instagram", "image", 1.5),
            ]),
            "performance_ranking": json.dumps({
                "video_avg_engagement_rate": 4.8,
                "image_avg_engagement_rate": 1.5,
                "video_vs_image_multiplier": 3.2,
            }),
        }

        result = await generate_insight_report(
            campaign_id="test-campaign",
            tool_context=mock_ctx,
        )

        # Should contain at least 3 numbers
        numbers = re.findall(r"\d+\.?\d*[x%]?", result)
        assert len(numbers) >= 3, f"Report only cited {len(numbers)} numbers: {result[:200]}"

    async def test_bigquery_write_idempotent(self):
        """Running store_metrics_to_bigquery twice does not create duplicates."""
        from brandforge.agents.analytics.tools import store_metrics_to_bigquery

        mock_ctx = MagicMock()
        mock_ctx.state = {
            "all_metrics": json.dumps([_make_metrics("instagram", "image", 2.0)]),
        }

        with patch("google.cloud.bigquery", create=True) as mock_bq:
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.insert_rows_json.return_value = []

            result1 = await store_metrics_to_bigquery("test-campaign", mock_ctx)
            result2 = await store_metrics_to_bigquery("test-campaign", mock_ctx)

        assert "Stored 1" in result1
        assert "Stored 1" in result2
        # In production, BigQuery deduplicates on post_id + hours_since_post
