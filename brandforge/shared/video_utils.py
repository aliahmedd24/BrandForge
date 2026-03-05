"""BrandForge video utilities — FFmpeg helpers for video composition.

Used by the Video Producer agent to merge Veo-generated video with
Cloud TTS voiceover audio into a final deliverable MP4.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def merge_video_audio(
    video_gcs: str,
    audio_gcs: str,
    output_gcs_path: str,
) -> str:
    """Merge a video file and audio file into a single MP4 using FFmpeg.

    Downloads video and audio from GCS, merges them locally with FFmpeg,
    then uploads the final result back to GCS.

    Args:
        video_gcs: GCS URI of the raw video (e.g. gs://bucket/video.mp4).
        audio_gcs: GCS URI of the audio file (e.g. gs://bucket/audio.mp3).
        output_gcs_path: Destination blob path in GCS for the merged video.

    Returns:
        Full gs:// URI of the merged video in GCS.

    Raises:
        RuntimeError: If FFmpeg merge fails.
    """
    from brandforge.shared.storage import download_blob, upload_blob
    from brandforge.shared.utils import gcs_uri_to_blob_path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        video_local = tmp / "video.mp4"
        audio_local = tmp / "audio.mp3"
        output_local = tmp / "final.mp4"

        # Download inputs from GCS
        logger.info("Downloading video from %s", video_gcs)
        video_bytes = await download_blob(gcs_uri_to_blob_path(video_gcs))
        video_local.write_bytes(video_bytes)

        logger.info("Downloading audio from %s", audio_gcs)
        audio_bytes = await download_blob(gcs_uri_to_blob_path(audio_gcs))
        audio_local.write_bytes(audio_bytes)

        # Merge with FFmpeg — use subprocess for better error capture than ffmpeg-python
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_local),
            "-i", str(audio_local),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_local),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=120
            )

            if process.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace")
                logger.error("FFmpeg merge failed (rc=%d): %s", process.returncode, stderr_text)
                raise RuntimeError(f"FFmpeg merge failed: {stderr_text[:500]}")

        except TimeoutError:
            logger.error("FFmpeg merge timed out after 120s")
            process.kill()
            raise RuntimeError("FFmpeg merge timed out after 120 seconds")

        # Upload merged result to GCS
        final_bytes = output_local.read_bytes()
        gcs_uri = await upload_blob(
            destination_path=output_gcs_path,
            data=final_bytes,
            content_type="video/mp4",
        )

        logger.info(
            "Merged video uploaded to %s (%.1f MB)",
            gcs_uri,
            len(final_bytes) / (1024 * 1024),
        )
        return gcs_uri


async def probe_has_audio_track(video_path_or_gcs: str) -> bool:
    """Check if a video file has an audio track using FFprobe.

    Can accept either a local file path or a GCS URI. If GCS URI,
    downloads the file first.

    Args:
        video_path_or_gcs: Local path or GCS URI of the video file.

    Returns:
        True if the video has at least one audio stream, False otherwise.
    """
    local_path = video_path_or_gcs

    # If it's a GCS URI, download to a temp file
    temp_dir = None
    if video_path_or_gcs.startswith("gs://"):
        from brandforge.shared.storage import download_blob
        from brandforge.shared.utils import gcs_uri_to_blob_path

        temp_dir = tempfile.mkdtemp()
        local_path = str(Path(temp_dir) / "probe_video.mp4")
        video_bytes = await download_blob(gcs_uri_to_blob_path(video_path_or_gcs))
        Path(local_path).write_bytes(video_bytes)

    try:
        ffprobe_cmd = [
            "ffprobe",
            "-v", "quiet",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            local_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *ffprobe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)

        output = stdout.decode("utf-8", errors="replace").strip()
        has_audio = "audio" in output
        logger.info("FFprobe audio check for %s: %s", video_path_or_gcs, has_audio)
        return has_audio

    except (TimeoutError, FileNotFoundError) as exc:
        logger.warning("FFprobe failed for %s: %s", video_path_or_gcs, exc)
        return False
    finally:
        # Clean up temp file if we created one
        if temp_dir:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
