"""Platform-specific asset format specifications.

Specs are config-driven — updating this file does not require code changes
in agent logic. Format Optimizer reads from PLATFORM_SPECS at runtime.
"""

from brandforge.shared.models import Platform

PLATFORM_SPECS: dict[str, dict[str, dict]] = {
    Platform.INSTAGRAM: {
        "feed": {
            "width": 1080,
            "height": 1080,
            "format": "jpeg",
            "max_size_mb": 8,
        },
        "story": {
            "width": 1080,
            "height": 1920,
            "format": "jpeg",
            "max_size_mb": 8,
        },
        "reel": {
            "width": 1080,
            "height": 1920,
            "format": "mp4",
            "max_duration_s": 90,
            "max_size_mb": 100,
        },
    },
    Platform.LINKEDIN: {
        "post": {
            "width": 1200,
            "height": 627,
            "format": "jpeg",
            "max_size_mb": 5,
        },
        "video": {
            "width": 1920,
            "height": 1080,
            "format": "mp4",
            "max_duration_s": 600,
            "max_size_mb": 200,
        },
    },
    Platform.TWITTER_X: {
        "post": {
            "width": 1600,
            "height": 900,
            "format": "jpeg",
            "max_size_mb": 5,
        },
        "video": {
            "width": 1280,
            "height": 720,
            "format": "mp4",
            "max_duration_s": 140,
            "max_size_mb": 512,
        },
    },
    Platform.TIKTOK: {
        "video": {
            "width": 1080,
            "height": 1920,
            "format": "mp4",
            "max_duration_s": 60,
            "max_size_mb": 287,
        },
    },
    Platform.FACEBOOK: {
        "feed": {
            "width": 1080,
            "height": 1080,
            "format": "jpeg",
            "max_size_mb": 8,
        },
        "video": {
            "width": 1280,
            "height": 720,
            "format": "mp4",
            "max_duration_s": 240,
            "max_size_mb": 200,
        },
    },
    Platform.YOUTUBE: {
        "video": {
            "width": 1920,
            "height": 1080,
            "format": "mp4",
            "max_duration_s": 900,
            "max_size_mb": 500,
        },
    },
}
