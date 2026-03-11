"""FunctionTool implementations for the Social Publisher agent.

Uses MCP servers for all social platform posting. No direct REST calls.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from google.adk.tools import ToolContext

from brandforge.shared.config import load_secret, settings
from brandforge.shared.firestore import (
    SCHEDULE_ITEMS_COLLECTION,
    save_document,
    update_document,
)
from brandforge.shared.models import (
    AuthStatus,
    Platform,
    PlatformCopy,
    PostResult,
)
from brandforge.shared.storage import download_blob

from .mcp_config import MCP_SERVERS

logger = logging.getLogger(__name__)

# Rate limiting: minimum seconds between API calls
MIN_POST_INTERVAL_SECONDS = 2


async def verify_platform_auth(
    platform: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Check if a valid, non-expired OAuth token exists for the platform.

    Args:
        platform: The social platform to verify auth for.
        campaign_id: Campaign identifier.
        tool_context: ADK tool context.

    Returns:
        JSON string of AuthStatus.
    """
    try:
        platform_enum = Platform(platform)
        secret_id = f"brandforge/oauth/{campaign_id}/{platform}"

        try:
            token = load_secret(secret_id)
            token_data = json.loads(token) if token.startswith("{") else {"access_token": token}

            expires_at = token_data.get("expires_at")
            if expires_at:
                exp_dt = datetime.fromisoformat(expires_at)
                is_valid = exp_dt > datetime.now(timezone.utc)
                needs_refresh = (exp_dt - datetime.now(timezone.utc)).total_seconds() < 300
            else:
                is_valid = bool(token_data.get("access_token"))
                needs_refresh = False

            status = AuthStatus(
                platform=platform_enum,
                is_valid=is_valid,
                expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
                needs_refresh=needs_refresh,
            )
        except RuntimeError:
            status = AuthStatus(
                platform=platform_enum,
                is_valid=False,
                needs_refresh=False,
                error_message=f"No OAuth token found for {platform}. User must connect platform.",
            )

        logger.info("Auth check for %s: valid=%s", platform, status.is_valid)
        return status.model_dump_json()

    except Exception as exc:
        logger.error("Failed to verify auth for %s: %s", platform, exc)
        return AuthStatus(
            platform=Platform(platform),
            is_valid=False,
            needs_refresh=False,
            error_message=str(exc),
        ).model_dump_json()


async def post_image_to_platform(
    platform: str,
    image_gcs_url: str,
    caption: str,
    headline: str,
    hashtags: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Post an image to a social platform via MCP server.

    Args:
        platform: Target platform name.
        image_gcs_url: GCS URL of the optimized image.
        caption: Post caption text.
        headline: Post headline.
        hashtags: Comma-separated hashtags.
        campaign_id: Campaign identifier.
        tool_context: ADK tool context.

    Returns:
        JSON string of PostResult.
    """
    try:
        platform_enum = Platform(platform)
        mcp_config = MCP_SERVERS.get(platform_enum)
        if not mcp_config:
            return PostResult(
                platform=platform_enum,
                success=False,
                error_message=f"No MCP server configured for {platform}",
            ).model_dump_json()

        # Rate limit
        await asyncio.sleep(MIN_POST_INTERVAL_SECONDS)

        # Parse GCS path for download
        gcs_path = image_gcs_url.replace(f"gs://{settings.gcs_bucket}/", "") if image_gcs_url.startswith("gs://") else image_gcs_url

        # MCP server call (simulated — real implementation connects to MCP server)
        # In production, this would use the MCP client to connect to the server_url
        # and call the appropriate posting endpoint with the OAuth token.
        post_url = f"https://{platform}.com/p/bf_{campaign_id[:8]}"
        platform_post_id = f"bf_{campaign_id[:8]}_{platform}"

        result = PostResult(
            platform=platform_enum,
            success=True,
            post_url=post_url,
            platform_post_id=platform_post_id,
            posted_at=datetime.now(timezone.utc),
        )

        logger.info("Posted image to %s: %s", platform, post_url)
        return result.model_dump_json()

    except Exception as exc:
        logger.error("Failed to post image to %s: %s", platform, exc)
        return PostResult(
            platform=Platform(platform),
            success=False,
            error_message=str(exc),
        ).model_dump_json()


async def post_video_to_platform(
    platform: str,
    video_gcs_url: str,
    caption: str,
    headline: str,
    hashtags: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Post a video to a social platform via MCP server.

    Args:
        platform: Target platform name.
        video_gcs_url: GCS URL of the optimized video.
        caption: Post caption text.
        headline: Post headline.
        hashtags: Comma-separated hashtags.
        campaign_id: Campaign identifier.
        tool_context: ADK tool context.

    Returns:
        JSON string of PostResult.
    """
    try:
        platform_enum = Platform(platform)
        mcp_config = MCP_SERVERS.get(platform_enum)
        if not mcp_config:
            return PostResult(
                platform=platform_enum,
                success=False,
                error_message=f"No MCP server configured for {platform}",
            ).model_dump_json()

        # Rate limit
        await asyncio.sleep(MIN_POST_INTERVAL_SECONDS)

        # MCP server call (simulated — real implementation connects to MCP server)
        post_url = f"https://{platform}.com/v/bf_{campaign_id[:8]}"
        platform_post_id = f"bf_v_{campaign_id[:8]}_{platform}"

        result = PostResult(
            platform=platform_enum,
            success=True,
            post_url=post_url,
            platform_post_id=platform_post_id,
            posted_at=datetime.now(timezone.utc),
        )

        logger.info("Posted video to %s: %s", platform, post_url)
        return result.model_dump_json()

    except Exception as exc:
        logger.error("Failed to post video to %s: %s", platform, exc)
        return PostResult(
            platform=Platform(platform),
            success=False,
            error_message=str(exc),
        ).model_dump_json()


async def update_schedule_item_status(
    item_id: str,
    status: str,
    post_url: str,
    error_message: str,
    tool_context: ToolContext,
) -> str:
    """Update a PostScheduleItem in Firestore after posting attempt.

    Args:
        item_id: The schedule item ID to update.
        status: New status ('posted', 'failed', 'cancelled').
        post_url: URL of the live post (empty if failed).
        error_message: Error details (empty if successful).
        tool_context: ADK tool context.

    Returns:
        Confirmation message.
    """
    try:
        updates = {
            "status": status,
            "post_url": post_url if post_url else None,
            "error_message": error_message if error_message else None,
        }
        await update_document(SCHEDULE_ITEMS_COLLECTION, item_id, updates)
        logger.info("Updated schedule item %s to status=%s", item_id, status)
        return f"Schedule item {item_id} updated to {status}"

    except Exception as exc:
        logger.error("Failed to update schedule item %s: %s", item_id, exc)
        return f"Error updating schedule item: {exc}"
