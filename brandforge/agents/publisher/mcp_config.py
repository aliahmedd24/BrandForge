"""MCP server configuration for social platform integrations.

All social posting goes through MCP servers — no direct REST calls.
"""

from brandforge.shared.models import Platform

MCP_SERVERS: dict[str, dict] = {
    Platform.INSTAGRAM: {
        "server_url": "https://mcp.instagram.com/v1",
        "auth_type": "oauth2",
        "scopes": ["instagram_basic", "instagram_content_publish"],
    },
    Platform.LINKEDIN: {
        "server_url": "https://mcp.linkedin.com/v1",
        "auth_type": "oauth2",
        "scopes": ["w_member_social", "r_basicprofile"],
    },
    Platform.TWITTER_X: {
        "server_url": "https://mcp.twitter.com/v1",
        "auth_type": "oauth2",
        "scopes": ["tweet.write", "users.read"],
    },
    Platform.TIKTOK: {
        "server_url": "https://mcp.tiktok.com/v1",
        "auth_type": "oauth2",
        "scopes": ["video.upload", "user.info.basic"],
    },
    Platform.FACEBOOK: {
        "server_url": "https://mcp.facebook.com/v1",
        "auth_type": "oauth2",
        "scopes": ["pages_manage_posts", "pages_read_engagement"],
    },
    Platform.YOUTUBE: {
        "server_url": "https://mcp.youtube.com/v1",
        "auth_type": "oauth2",
        "scopes": ["youtube.upload", "youtube.readonly"],
    },
}
