"""BrandForge shared utilities — common helpers used across all agents.

Extracted from brand_strategist/tools.py to avoid duplication.
All agent tool modules should import helpers from here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def gcs_uri_to_blob_path(gcs_uri: str) -> str:
    """Convert a gs://bucket/path URI to just the blob path.

    Args:
        gcs_uri: Full GCS URI, e.g. 'gs://brandforge-assets/campaigns/abc/voice.webm'.

    Returns:
        The blob path after the bucket name, e.g. 'campaigns/abc/voice.webm'.
        If input doesn't start with gs://, returns it as-is.
    """
    if gcs_uri.startswith("gs://"):
        parts = gcs_uri[5:].split("/", 1)
        return parts[1] if len(parts) > 1 else ""
    return gcs_uri


def strip_json_fences(text: str) -> str:
    """Remove markdown JSON code fences if present.

    Handles ```json ... ``` and plain ``` ... ``` wrapping that LLMs
    sometimes add around JSON responses.

    Args:
        text: Raw text possibly wrapped in markdown code fences.

    Returns:
        Clean JSON string with fences stripped.
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def guess_mime_type(blob_path: str) -> str:
    """Guess MIME type from file extension.

    Args:
        blob_path: The file path or GCS blob path.

    Returns:
        MIME type string. Defaults to 'image/jpeg' for unknown extensions.
    """
    lower = blob_path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".mp3"):
        return "audio/mpeg"
    if lower.endswith(".wav"):
        return "audio/wav"
    if lower.endswith(".webm"):
        return "audio/webm"
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".json"):
        return "application/json"
    return "image/jpeg"


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 4.0,
    max_delay: float = 60.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    operation_name: str = "operation",
    **kwargs: Any,
) -> Any:
    """Execute an async function with exponential backoff retry.

    Retries the given async callable on transient failures with
    exponentially increasing delays (base_delay * 2^attempt).

    Args:
        func: The async callable to execute.
        *args: Positional arguments passed to func.
        max_retries: Maximum number of retry attempts (default 3).
        base_delay: Initial delay in seconds before first retry (default 4).
        max_delay: Maximum delay cap in seconds (default 60).
        retry_on: Tuple of exception types to retry on.
        operation_name: Human-readable name for logging.
        **kwargs: Keyword arguments passed to func.

    Returns:
        The return value of func on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retry_on as exc:
            last_exception = exc
            if attempt == max_retries:
                logger.error(
                    "%s failed after %d attempts: %s",
                    operation_name,
                    max_retries + 1,
                    exc,
                )
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "%s attempt %d/%d failed: %s — retrying in %.1fs",
                operation_name,
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checker
    raise last_exception  # type: ignore[misc]
