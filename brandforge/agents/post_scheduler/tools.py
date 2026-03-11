"""FunctionTool implementations for the Post Scheduler agent.

Computes optimal posting schedules, generates .ics calendars,
and creates Cloud Scheduler jobs.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.adk.tools import ToolContext

from brandforge.shared.config import settings
from brandforge.shared.firestore import (
    POSTING_CALENDARS_COLLECTION,
    save_document,
)
from brandforge.shared.models import (
    AudiencePersona,
    Platform,
    PostableAsset,
    PostingCalendar,
    PostingWindow,
    PostScheduleItem,
)
from brandforge.shared.storage import upload_blob

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


async def research_optimal_posting_times(
    platforms: list[str],
    audience_description: str,
    campaign_goal: str,
    tool_context: ToolContext,
) -> str:
    """Use Gemini with Google Search grounding to find optimal posting times.

    Args:
        platforms: List of platform names to research.
        audience_description: Description of the target audience.
        campaign_goal: The campaign's primary objective.
        tool_context: ADK tool context.

    Returns:
        JSON string of posting windows per platform.
    """
    try:
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        client = _get_genai_client()
        search_tool = Tool(google_search=GoogleSearch())

        prompt = (
            f"Research the current best posting times for social media platforms: "
            f"{', '.join(platforms)}. Target audience: {audience_description}. "
            f"Campaign goal: {campaign_goal}. "
            f"For each platform, provide the top 3 best days and hours (UTC) to post, "
            f"with rationale based on current engagement data. "
            f"Return structured JSON with platform as key and list of "
            f"{{day_of_week, hour_utc, rationale, expected_reach_multiplier}} objects."
        )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=prompt,
            config=GenerateContentConfig(
                tools=[search_tool],
                temperature=0.3,
            ),
        )

        result_text = response.text if response.text else "{}"

        # Store in session state for calendar generation
        tool_context.state["posting_windows_raw"] = result_text
        logger.info("Researched posting times for %d platforms", len(platforms))
        return result_text

    except Exception as exc:
        logger.error("Failed to research posting times: %s", exc)
        # Fallback: return reasonable defaults
        fallback = {}
        for p in platforms:
            fallback[p] = [
                {"day_of_week": "tuesday", "hour_utc": 14, "rationale": "Default mid-week afternoon", "expected_reach_multiplier": 1.2},
                {"day_of_week": "thursday", "hour_utc": 10, "rationale": "Default Thursday morning", "expected_reach_multiplier": 1.1},
                {"day_of_week": "saturday", "hour_utc": 11, "rationale": "Default weekend late morning", "expected_reach_multiplier": 1.0},
            ]
        return json.dumps(fallback)


async def generate_posting_calendar(
    campaign_id: str,
    platforms: list[str],
    duration_days: int,
    tool_context: ToolContext,
) -> str:
    """Distribute assets across a posting calendar using pacing rules.

    Args:
        campaign_id: Campaign identifier.
        platforms: Target platforms.
        duration_days: Calendar duration in days (default 14).
        tool_context: ADK tool context for state access.

    Returns:
        JSON string of the generated PostingCalendar.
    """
    try:
        now = datetime.now(timezone.utc)
        start_date = now + timedelta(hours=1)  # Start 1 hour from now
        end_date = start_date + timedelta(days=duration_days)

        # Build schedule items with pacing
        items: list[dict] = []
        day_offset = 0
        platform_last_type: dict[str, str] = {}
        platform_weekly_count: dict[str, int] = {}

        for day_offset in range(duration_days):
            current_date = start_date + timedelta(days=day_offset)
            week_num = day_offset // 7

            for platform in platforms:
                week_key = f"{platform}_{week_num}"
                count = platform_weekly_count.get(week_key, 0)
                if count >= 3:
                    continue  # Max 3 posts per platform per week

                # Alternate asset types
                last_type = platform_last_type.get(platform, "image")
                asset_type = "video" if last_type == "image" else "image"

                # Pick a reasonable hour based on day
                hour = 10 + (day_offset % 8)  # Varies between 10-17 UTC

                scheduled_at = current_date.replace(hour=hour, minute=0, second=0)

                items.append({
                    "id": str(uuid.uuid4()),
                    "campaign_id": campaign_id,
                    "asset": {
                        "asset_id": f"placeholder_{platform}_{day_offset}",
                        "asset_type": asset_type,
                        "platform": platform,
                        "gcs_url": "",
                        "copy": {
                            "platform": platform,
                            "caption": "",
                            "headline": "",
                            "hashtags": [],
                            "cta_text": "",
                            "character_count": 0,
                            "brand_voice_score": 0.0,
                        },
                    },
                    "scheduled_at": scheduled_at.isoformat(),
                    "platform": platform,
                    "status": "scheduled",
                })

                platform_last_type[platform] = asset_type
                platform_weekly_count[week_key] = count + 1

        calendar = {
            "id": str(uuid.uuid4()),
            "campaign_id": campaign_id,
            "items": items,
            "total_posts": len(items),
            "platforms": platforms,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        # Store in Firestore
        await save_document(
            POSTING_CALENDARS_COLLECTION, calendar["id"], calendar,
        )

        tool_context.state["posting_calendar"] = json.dumps(calendar)
        logger.info("Generated posting calendar: %d posts over %d days", len(items), duration_days)
        return json.dumps(calendar)

    except Exception as exc:
        logger.error("Failed to generate posting calendar: %s", exc)
        return f"Error generating calendar: {exc}"


async def export_calendar_ics(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Generate an .ics calendar file and upload to GCS.

    Args:
        campaign_id: Campaign identifier.
        tool_context: ADK tool context for state access.

    Returns:
        GCS URL of the .ics file.
    """
    try:
        from icalendar import Calendar, Event

        calendar_json = tool_context.state.get("posting_calendar", "{}")
        calendar_data = json.loads(calendar_json)

        cal = Calendar()
        cal.add("prodid", "-//BrandForge//Campaign Posting Schedule//EN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("x-wr-calname", f"BrandForge Campaign {campaign_id}")

        for item in calendar_data.get("items", []):
            event = Event()
            event.add("summary", f"Post to {item['platform']}: {item['asset']['asset_type']}")
            scheduled = datetime.fromisoformat(item["scheduled_at"])
            event.add("dtstart", scheduled)
            event.add("dtend", scheduled + timedelta(minutes=15))
            event.add("uid", f"{item['id']}@brandforge")
            event.add("description", f"Campaign: {campaign_id}\nPlatform: {item['platform']}")
            cal.add_component(event)

        ics_bytes = cal.to_ical()

        dest_path = f"campaigns/{campaign_id}/schedule/calendar.ics"
        gcs_url = await asyncio.to_thread(
            upload_blob, ics_bytes, dest_path, "text/calendar",
        )

        # Update calendar with ICS URL
        calendar_data["ics_gcs_url"] = gcs_url
        tool_context.state["posting_calendar"] = json.dumps(calendar_data)

        logger.info("Exported .ics calendar to %s", gcs_url)
        return gcs_url

    except Exception as exc:
        logger.error("Failed to export ICS calendar: %s", exc)
        return f"Error exporting calendar: {exc}"


async def schedule_cloud_jobs(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Create Cloud Scheduler jobs for each scheduled post.

    Args:
        campaign_id: Campaign identifier.
        tool_context: ADK tool context for state access.

    Returns:
        JSON list of created Cloud Scheduler job names.
    """
    try:
        from google.cloud import scheduler_v1

        calendar_json = tool_context.state.get("posting_calendar", "{}")
        calendar_data = json.loads(calendar_json)

        client = scheduler_v1.CloudSchedulerClient()
        parent = f"projects/{settings.gcp_project}/locations/{settings.gcp_region}"
        job_names: list[str] = []

        for item in calendar_data.get("items", []):
            scheduled = datetime.fromisoformat(item["scheduled_at"])
            # Cron expression: minute hour day month *
            cron = f"{scheduled.minute} {scheduled.hour} {scheduled.day} {scheduled.month} *"

            job_name = f"brandforge-post-{campaign_id[:8]}-{item['id'][:8]}"
            job = scheduler_v1.Job(
                name=f"{parent}/jobs/{job_name}",
                schedule=cron,
                time_zone="UTC",
                http_target=scheduler_v1.HttpTarget(
                    uri=f"https://brandforge-api.run.app/campaigns/{campaign_id}/publish/{item['id']}",
                    http_method=scheduler_v1.HttpMethod.POST,
                    body=json.dumps({"item_id": item["id"]}).encode(),
                    headers={"Content-Type": "application/json"},
                ),
            )

            try:
                created = client.create_job(parent=parent, job=job)
                job_names.append(created.name)
            except Exception as job_exc:
                logger.warning("Failed to create scheduler job %s: %s", job_name, job_exc)
                job_names.append(f"FAILED:{job_name}")

        logger.info("Created %d Cloud Scheduler jobs for campaign %s", len(job_names), campaign_id)
        return json.dumps(job_names)

    except Exception as exc:
        logger.error("Failed to schedule cloud jobs: %s", exc)
        return f"Error scheduling jobs: {exc}"
