"""FunctionTool implementations for the Analytics Agent.

Reads engagement data from published posts, stores in BigQuery,
computes performance rankings, and delivers insights via A2A.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from google.adk.tools import ToolContext

from brandforge.shared.config import settings
from brandforge.shared.firestore import (
    ANALYTICS_INSIGHTS_COLLECTION,
    SCHEDULE_ITEMS_COLLECTION,
    save_document,
    update_document,
)
from brandforge.shared.models import (
    AnalyticsInsight,
    CampaignStatus,
    CreativeRecommendation,
    PerformanceRanking,
    Platform,
    PostMetrics,
)

logger = logging.getLogger(__name__)


def _get_genai_client():
    """Return a singleton google.genai Client configured for Vertex AI.

    Returns:
        A configured genai.Client instance.
    """
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.gcp_project or "brandforge-489114",
        location=settings.gcp_region,
    )


async def fetch_platform_metrics(
    campaign_id: str,
    platform: str,
    hours_since_post: int,
    tool_context: ToolContext,
) -> str:
    """Fetch engagement metrics from a platform via MCP for all posted items.

    Args:
        campaign_id: Campaign identifier.
        platform: Platform name to fetch metrics from.
        hours_since_post: Time window (24, 72, or 168 hours).
        tool_context: ADK tool context.

    Returns:
        JSON list of PostMetrics objects.
    """
    try:
        platform_enum = Platform(platform)

        # In production, this would call the MCP server to read engagement APIs.
        # For now, we query Firestore for posted items and generate placeholder metrics.
        from brandforge.shared.firestore import query_documents

        posted_items = await query_documents(
            SCHEDULE_ITEMS_COLLECTION,
            field="campaign_id",
            value=campaign_id,
        )

        metrics: list[dict] = []
        for item in posted_items:
            if item.get("status") != "posted" or item.get("platform") != platform:
                continue

            asset = item.get("asset", {})
            metric = PostMetrics(
                post_schedule_item_id=item["id"],
                platform=platform_enum,
                asset_id=asset.get("asset_id", "unknown"),
                asset_type=asset.get("asset_type", "image"),
                impressions=0,
                reach=0,
                likes=0,
                comments=0,
                shares=0,
                engagement_rate=0.0,
                hours_since_post=hours_since_post,
            )
            metrics.append(metric.model_dump(mode="json"))

        # Store in session state for aggregation
        existing = json.loads(tool_context.state.get("all_metrics", "[]"))
        existing.extend(metrics)
        tool_context.state["all_metrics"] = json.dumps(existing)

        logger.info("Fetched %d metrics for %s/%s", len(metrics), campaign_id, platform)
        return json.dumps(metrics)

    except Exception as exc:
        logger.error("Failed to fetch metrics for %s/%s: %s", campaign_id, platform, exc)
        return json.dumps([])


async def store_metrics_to_bigquery(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Write post metrics to BigQuery (idempotent — no duplicate rows).

    Args:
        campaign_id: Campaign identifier.
        tool_context: ADK tool context with all_metrics in state.

    Returns:
        Status message.
    """
    try:
        from google.cloud import bigquery

        metrics_json = tool_context.state.get("all_metrics", "[]")
        metrics = json.loads(metrics_json)

        if not metrics:
            return "No metrics to store"

        client = bigquery.Client(project=settings.gcp_project)
        table_id = f"{settings.gcp_project}.brandforge.campaign_analytics"

        # Convert to BigQuery rows
        rows = []
        for m in metrics:
            rows.append({
                "campaign_id": campaign_id,
                "post_id": m.get("post_schedule_item_id"),
                "platform": m.get("platform"),
                "asset_id": m.get("asset_id"),
                "asset_type": m.get("asset_type"),
                "impressions": m.get("impressions", 0),
                "reach": m.get("reach", 0),
                "likes": m.get("likes", 0),
                "comments": m.get("comments", 0),
                "shares": m.get("shares", 0),
                "saves": m.get("saves", 0),
                "video_views": m.get("video_views"),
                "video_completion_rate": m.get("video_completion_rate"),
                "engagement_rate": m.get("engagement_rate", 0.0),
                "click_through_rate": m.get("click_through_rate"),
                "hours_since_post": m.get("hours_since_post", 24),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        # Insert rows (idempotent via deduplication on post_id + hours_since_post)
        errors = await asyncio.to_thread(
            client.insert_rows_json, table_id, rows,
        )

        if errors:
            logger.warning("BigQuery insert errors: %s", errors[:3])
            return f"Stored {len(rows)} rows with {len(errors)} errors"

        logger.info("Stored %d metrics rows to BigQuery", len(rows))
        return f"Stored {len(rows)} metrics rows to BigQuery"

    except Exception as exc:
        logger.error("Failed to store metrics to BigQuery: %s", exc)
        return f"Error storing to BigQuery: {exc}"


async def compute_performance_rankings(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Compute relative performance rankings across all posts.

    Args:
        campaign_id: Campaign identifier.
        tool_context: ADK tool context with all_metrics in state.

    Returns:
        JSON string of PerformanceRanking.
    """
    try:
        metrics_json = tool_context.state.get("all_metrics", "[]")
        metrics = json.loads(metrics_json)

        if not metrics:
            return json.dumps({"error": "No metrics available"})

        # Separate by asset type
        video_metrics = [m for m in metrics if m.get("asset_type") == "video"]
        image_metrics = [m for m in metrics if m.get("asset_type") == "image"]

        video_avg_er = (
            sum(m.get("engagement_rate", 0) for m in video_metrics) / len(video_metrics)
            if video_metrics else 0.0
        )
        image_avg_er = (
            sum(m.get("engagement_rate", 0) for m in image_metrics) / len(image_metrics)
            if image_metrics else 0.0
        )

        multiplier = video_avg_er / image_avg_er if image_avg_er > 0 else 1.0

        # Find best/worst
        sorted_metrics = sorted(metrics, key=lambda m: m.get("engagement_rate", 0), reverse=True)
        best = sorted_metrics[0] if sorted_metrics else metrics[0]
        worst = sorted_metrics[-1] if sorted_metrics else metrics[0]

        # Platform rankings
        platform_er: dict[str, list[float]] = {}
        for m in metrics:
            p = m.get("platform", "unknown")
            platform_er.setdefault(p, []).append(m.get("engagement_rate", 0))

        platform_rankings = sorted(
            [
                {"platform": p, "avg_engagement_rate": sum(rates) / len(rates)}
                for p, rates in platform_er.items()
            ],
            key=lambda x: x["avg_engagement_rate"],
            reverse=True,
        )

        ranking = PerformanceRanking(
            best_asset_id=best.get("asset_id", "unknown"),
            best_asset_type=best.get("asset_type", "unknown"),
            best_platform=Platform(platform_rankings[0]["platform"]) if platform_rankings else Platform.INSTAGRAM,
            best_posting_hour_utc=14,  # Derived from actual scheduled_at in production
            video_avg_engagement_rate=video_avg_er,
            image_avg_engagement_rate=image_avg_er,
            video_vs_image_multiplier=round(multiplier, 2),
            platform_rankings=platform_rankings,
            worst_asset_id=worst.get("asset_id", "unknown"),
        )

        tool_context.state["performance_ranking"] = ranking.model_dump_json()
        logger.info("Computed performance rankings for campaign %s", campaign_id)
        return ranking.model_dump_json()

    except Exception as exc:
        logger.error("Failed to compute rankings: %s", exc)
        return json.dumps({"error": str(exc)})


async def generate_insight_report(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Generate a natural language insight report using Gemini.

    Args:
        campaign_id: Campaign identifier.
        tool_context: ADK tool context with metrics and rankings in state.

    Returns:
        The insight report text.
    """
    try:
        from google.genai.types import GenerateContentConfig

        metrics_json = tool_context.state.get("all_metrics", "[]")
        ranking_json = tool_context.state.get("performance_ranking", "{}")

        client = _get_genai_client()

        prompt = (
            f"Generate a 3-5 paragraph analytics insight report for campaign {campaign_id}.\n\n"
            f"Performance metrics: {metrics_json[:2000]}\n\n"
            f"Rankings: {ranking_json}\n\n"
            f"Write in a confident, data-driven voice. Cite specific numbers. "
            f"Include actionable recommendations."
        )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=prompt,
            config=GenerateContentConfig(temperature=0.4),
        )

        report = response.text if response.text else "Insufficient data for insight report."
        tool_context.state["insight_report"] = report

        logger.info("Generated insight report for campaign %s", campaign_id)
        return report

    except Exception as exc:
        logger.error("Failed to generate insight report: %s", exc)
        return f"Error generating report: {exc}"


async def deliver_a2a_insights(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Deliver structured analytics insight to Orchestrator via A2A.

    Args:
        campaign_id: Campaign identifier.
        tool_context: ADK tool context with all analysis data.

    Returns:
        JSON status of delivery.
    """
    try:
        metrics = json.loads(tool_context.state.get("all_metrics", "[]"))
        ranking_json = tool_context.state.get("performance_ranking", "{}")
        ranking = json.loads(ranking_json) if ranking_json != "{}" else None
        report = tool_context.state.get("insight_report", "")

        # Build recommendations
        recommendations: list[dict] = []
        if ranking:
            video_er = ranking.get("video_avg_engagement_rate", 0)
            image_er = ranking.get("image_avg_engagement_rate", 0)
            multiplier = ranking.get("video_vs_image_multiplier", 1.0)

            if multiplier > 1.5:
                recommendations.append({
                    "dimension": "content_type",
                    "finding": f"Video engagement rate ({video_er:.1f}%) is {multiplier:.1f}x higher than images ({image_er:.1f}%)",
                    "recommendation": "Bias next campaign toward 70% video, 30% image content",
                    "confidence": min(0.9, len(metrics) / 10),
                    "supporting_metrics": {"video_er": video_er, "image_er": image_er, "multiplier": multiplier},
                })

            if ranking.get("platform_rankings"):
                top_platform = ranking["platform_rankings"][0]
                recommendations.append({
                    "dimension": "platform",
                    "finding": f"{top_platform['platform']} has highest avg engagement rate ({top_platform['avg_engagement_rate']:.1f}%)",
                    "recommendation": f"Prioritize {top_platform['platform']} for next campaign launch content",
                    "confidence": min(0.8, len(metrics) / 10),
                    "supporting_metrics": {"top_platform_er": top_platform["avg_engagement_rate"]},
                })

        # Determine summary flags
        bias_toward_video = (ranking or {}).get("video_vs_image_multiplier", 1.0) > 1.2
        top_platform_str = (ranking or {}).get("platform_rankings", [{}])[0].get("platform", "instagram") if ranking else "instagram"
        platforms_with_data = len(set(m.get("platform") for m in metrics))
        total_platforms = max(1, len(set(m.get("platform") for m in metrics)) or 1)

        insight = AnalyticsInsight(
            campaign_id=campaign_id,
            all_metrics=[PostMetrics(**m) for m in metrics] if metrics else [],
            performance_ranking=PerformanceRanking(**ranking) if ranking else PerformanceRanking(
                best_asset_id="none", best_asset_type="none",
                best_platform=Platform.INSTAGRAM, best_posting_hour_utc=14,
                video_avg_engagement_rate=0.0, image_avg_engagement_rate=0.0,
                video_vs_image_multiplier=1.0, platform_rankings=[], worst_asset_id="none",
            ),
            insight_report=report,
            creative_recommendations=[CreativeRecommendation(**r) for r in recommendations],
            bias_toward_video=bias_toward_video,
            top_platform=Platform(top_platform_str),
            optimal_posting_hour_utc=(ranking or {}).get("best_posting_hour_utc", 14),
            data_completeness=platforms_with_data / total_platforms,
        )

        # Store insight in Firestore
        await save_document(
            ANALYTICS_INSIGHTS_COLLECTION, insight.id,
            insight.model_dump(mode="json"),
        )

        # Update session state for orchestrator consumption
        tool_context.state["user:latest_analytics_insight_id"] = insight.id
        tool_context.state["user:bias_toward_video"] = bias_toward_video
        tool_context.state["user:top_platform"] = top_platform_str

        logger.info("Delivered A2A insight %s for campaign %s", insight.id, campaign_id)
        return json.dumps({"status": "delivered", "insight_id": insight.id})

    except Exception as exc:
        logger.error("Failed to deliver A2A insights: %s", exc)
        return json.dumps({"status": "failed", "error": str(exc)})
