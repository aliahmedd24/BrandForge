"""FunctionTool implementations for the Format Optimizer agent.

Handles image resizing via Pillow and video transcoding via FFmpeg
to meet platform-specific format requirements.
"""

import asyncio
import io
import logging
import subprocess
import tempfile
from typing import Optional

from google.adk.tools import ToolContext

from brandforge.config.platform_specs import PLATFORM_SPECS
from brandforge.shared.config import settings
from brandforge.shared.models import Platform
from brandforge.shared.storage import download_blob, upload_blob

logger = logging.getLogger(__name__)


def _gcs_path_from_url(gcs_url: str) -> str:
    """Extract the object path from a gs:// URL.

    Args:
        gcs_url: A GCS URL like gs://bucket/path/to/file.

    Returns:
        The object path portion (e.g. 'path/to/file').
    """
    if gcs_url.startswith("gs://"):
        parts = gcs_url.replace("gs://", "").split("/", 1)
        return parts[1] if len(parts) > 1 else ""
    return gcs_url


async def optimize_image_for_platform(
    image_gcs_url: str,
    platform: str,
    use_case: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Download image, resize with Pillow (LANCZOS), convert format, re-upload.

    Args:
        image_gcs_url: GCS URL of the source image.
        platform: Target platform name.
        use_case: Platform use case (e.g. 'feed', 'story', 'post').
        campaign_id: Campaign identifier.
        tool_context: ADK tool context for state access.

    Returns:
        GCS URL of the optimized image, or error string on failure.
    """
    try:
        from PIL import Image

        platform_enum = Platform(platform)
        specs = PLATFORM_SPECS.get(platform_enum, {})
        spec = specs.get(use_case)
        if not spec:
            return f"Error: No spec found for {platform}/{use_case}"

        target_w = spec["width"]
        target_h = spec["height"]
        target_format = spec.get("format", "jpeg").upper()
        max_size_bytes = spec.get("max_size_mb", 10) * 1024 * 1024

        # Download source image
        source_path = _gcs_path_from_url(image_gcs_url)
        image_bytes = await asyncio.to_thread(download_blob, source_path)

        # Resize with Pillow
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        img = img.resize((target_w, target_h), Image.LANCZOS)

        # Compress to meet size limit
        quality = 95
        while quality >= 20:
            buf = io.BytesIO()
            img.save(buf, format=target_format, quality=quality, optimize=True)
            if buf.tell() <= max_size_bytes:
                break
            quality -= 5

        buf.seek(0)
        optimized_bytes = buf.read()

        # Upload optimized image
        ext = "jpg" if target_format == "JPEG" else target_format.lower()
        dest_path = f"campaigns/{campaign_id}/optimized/{platform}/{use_case}.{ext}"
        content_type = f"image/{ext}"
        gcs_url = await asyncio.to_thread(
            upload_blob, optimized_bytes, dest_path, content_type,
        )

        logger.info(
            "Optimized image for %s/%s: %dx%d, %d bytes",
            platform, use_case, target_w, target_h, len(optimized_bytes),
        )
        return gcs_url

    except Exception as exc:
        logger.error("Failed to optimize image for %s/%s: %s", platform, use_case, exc)
        return f"Error optimizing image: {exc}"


async def optimize_video_for_platform(
    video_gcs_url: str,
    platform: str,
    use_case: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Download video, transcode with FFmpeg to platform specs, re-upload.

    Args:
        video_gcs_url: GCS URL of the source video.
        platform: Target platform name.
        use_case: Platform use case (e.g. 'reel', 'video').
        campaign_id: Campaign identifier.
        tool_context: ADK tool context for state access.

    Returns:
        GCS URL of the optimized video, or error string on failure.
    """
    try:
        platform_enum = Platform(platform)
        specs = PLATFORM_SPECS.get(platform_enum, {})
        spec = specs.get(use_case)
        if not spec:
            return f"Error: No spec found for {platform}/{use_case}"

        target_w = spec["width"]
        target_h = spec["height"]
        max_duration = spec.get("max_duration_s", 600)
        max_size_bytes = spec.get("max_size_mb", 200) * 1024 * 1024

        # Download source video
        source_path = _gcs_path_from_url(video_gcs_url)
        video_bytes = await asyncio.to_thread(download_blob, source_path)

        # Write to temp file, transcode with FFmpeg
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as src_f:
            src_f.write(video_bytes)
            src_path = src_f.name

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as dst_f:
            dst_path = dst_f.name

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", src_path,
            "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2",
            "-t", str(max_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            dst_path,
        ]

        result = await asyncio.to_thread(
            subprocess.run, ffmpeg_cmd,
            capture_output=True, text=True, timeout=300,
        )

        if result.returncode != 0:
            logger.error("FFmpeg error: %s", result.stderr[:500])
            return f"Error: FFmpeg transcoding failed: {result.stderr[:200]}"

        # Read optimized video
        with open(dst_path, "rb") as f:
            optimized_bytes = f.read()

        if len(optimized_bytes) > max_size_bytes:
            logger.warning(
                "Optimized video exceeds size limit: %d > %d",
                len(optimized_bytes), max_size_bytes,
            )

        # Upload optimized video
        dest = f"campaigns/{campaign_id}/optimized/{platform}/{use_case}.mp4"
        gcs_url = await asyncio.to_thread(
            upload_blob, optimized_bytes, dest, "video/mp4",
        )

        logger.info(
            "Optimized video for %s/%s: %dx%d, %d bytes",
            platform, use_case, target_w, target_h, len(optimized_bytes),
        )
        return gcs_url

    except Exception as exc:
        logger.error("Failed to optimize video for %s/%s: %s", platform, use_case, exc)
        return f"Error optimizing video: {exc}"
