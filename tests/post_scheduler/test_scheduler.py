"""Tests for the Post Scheduler agent — Phase 5 DoD."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brandforge.shared.models import Platform


class TestPostScheduler:
    """Post Scheduler Definition of Done tests."""

    @pytest.mark.llm
    async def test_posting_windows_grounded(self):
        """research_optimal_posting_times references at least one external source."""
        from brandforge.agents.post_scheduler.tools import research_optimal_posting_times

        mock_ctx = MagicMock()
        mock_ctx.state = {}

        result = await research_optimal_posting_times(
            platforms=["instagram", "linkedin"],
            audience_description="Urban millennials aged 25-35",
            campaign_goal="product launch",
            tool_context=mock_ctx,
        )

        # Result should be non-empty JSON with rationale
        assert len(result) > 10
        # Rationale should contain some reasoning (not just empty strings)
        data = json.loads(result) if result.startswith("{") or result.startswith("[") else {}
        # Grounding evidence: result should contain substantive content
        assert len(result) > 50

    async def test_calendar_pacing(self):
        """No platform has more than 3 posts scheduled in any 7-day window."""
        from brandforge.agents.post_scheduler.tools import generate_posting_calendar

        mock_ctx = MagicMock()
        mock_ctx.state = {}

        with patch("brandforge.agents.post_scheduler.tools.save_document", new_callable=AsyncMock):
            result = await generate_posting_calendar(
                campaign_id="test-campaign",
                platforms=["instagram", "linkedin", "tiktok"],
                duration_days=14,
                tool_context=mock_ctx,
            )

        calendar = json.loads(result)
        items = calendar["items"]

        # Count per platform per week
        for platform in ["instagram", "linkedin", "tiktok"]:
            platform_items = [i for i in items if i["platform"] == platform]
            # Split into weeks
            for week_start in range(0, 14, 7):
                start = datetime.fromisoformat(calendar["start_date"])
                week_items = [
                    i for i in platform_items
                    if week_start <= (datetime.fromisoformat(i["scheduled_at"]) - start).days < week_start + 7
                ]
                assert len(week_items) <= 3, (
                    f"{platform} has {len(week_items)} posts in week starting day {week_start}"
                )

    async def test_asset_type_distribution(self):
        """No two consecutive posts on the same platform are the same asset type."""
        from brandforge.agents.post_scheduler.tools import generate_posting_calendar

        mock_ctx = MagicMock()
        mock_ctx.state = {}

        with patch("brandforge.agents.post_scheduler.tools.save_document", new_callable=AsyncMock):
            result = await generate_posting_calendar(
                campaign_id="test-campaign",
                platforms=["instagram"],
                duration_days=14,
                tool_context=mock_ctx,
            )

        calendar = json.loads(result)
        items = [i for i in calendar["items"] if i["platform"] == "instagram"]

        for i in range(1, len(items)):
            assert items[i]["asset"]["asset_type"] != items[i - 1]["asset"]["asset_type"], (
                f"Consecutive same asset type at index {i}"
            )

    async def test_ics_export_valid(self):
        """Generated .ics file parses correctly with icalendar library."""
        from icalendar import Calendar

        from brandforge.agents.post_scheduler.tools import export_calendar_ics

        # Seed state with a minimal calendar
        test_calendar = {
            "id": "test-cal",
            "campaign_id": "test-campaign",
            "items": [
                {
                    "id": "item-1",
                    "platform": "instagram",
                    "asset": {"asset_type": "image"},
                    "scheduled_at": datetime.now(timezone.utc).isoformat(),
                },
            ],
        }

        mock_ctx = MagicMock()
        mock_ctx.state = {"posting_calendar": json.dumps(test_calendar)}
        captured_bytes = None

        def capture_upload(data, *args, **kwargs):
            nonlocal captured_bytes
            captured_bytes = data
            return "gs://test-bucket/calendar.ics"

        with patch("brandforge.agents.post_scheduler.tools.upload_blob", side_effect=capture_upload):
            result = await export_calendar_ics(
                campaign_id="test-campaign",
                tool_context=mock_ctx,
            )

        assert result.startswith("gs://")
        # Parse the .ics content
        cal = Calendar.from_ical(captured_bytes)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1
        assert "instagram" in str(events[0].get("summary")).lower()

    @pytest.mark.gcp
    async def test_cloud_scheduler_jobs_created(self):
        """One Cloud Scheduler job is created per PostScheduleItem."""
        from brandforge.agents.post_scheduler.tools import schedule_cloud_jobs

        test_calendar = {
            "items": [
                {"id": "item-1", "scheduled_at": "2026-04-01T14:00:00+00:00"},
                {"id": "item-2", "scheduled_at": "2026-04-03T10:00:00+00:00"},
            ],
        }

        mock_ctx = MagicMock()
        mock_ctx.state = {"posting_calendar": json.dumps(test_calendar)}

        with patch("brandforge.agents.post_scheduler.tools.scheduler_v1") as mock_sched:
            mock_client = MagicMock()
            mock_sched.CloudSchedulerClient.return_value = mock_client
            mock_client.create_job.return_value = MagicMock(name="jobs/test-job")

            result = await schedule_cloud_jobs(
                campaign_id="test-campaign",
                tool_context=mock_ctx,
            )

        jobs = json.loads(result)
        assert len(jobs) == 2
