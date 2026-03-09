"""Google Cloud Storage client helpers for BrandForge.

Provides a client singleton and helpers for uploading, downloading,
and generating signed URLs for campaign assets.
"""

import logging
from typing import Optional

from google.cloud import storage

from .config import settings

logger = logging.getLogger(__name__)

# ── Client singleton ────────────────────────────────────────────────────

_client: Optional[storage.Client] = None


def get_storage_client() -> storage.Client:
    """Return the GCS client singleton.

    Returns:
        A storage.Client instance.
    """
    global _client
    if _client is None:
        _client = storage.Client(project=settings.gcp_project or None)
        logger.info("GCS Client initialized")
    return _client


# ── Helpers ──────────────────────────────────────────────────────────────


def upload_blob(
    source_data: bytes,
    destination_path: str,
    content_type: str = "application/octet-stream",
    bucket_name: Optional[str] = None,
) -> str:
    """Upload bytes to GCS and return the gs:// URI.

    Args:
        source_data: The file content as bytes.
        destination_path: The object path within the bucket (e.g. "campaigns/abc/image.png").
        content_type: The MIME type of the object.
        bucket_name: Override the default bucket name.

    Returns:
        The gs:// URI of the uploaded object.
    """
    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name or settings.gcs_bucket)
        blob = bucket.blob(destination_path)
        blob.upload_from_string(source_data, content_type=content_type)
        uri = f"gs://{bucket.name}/{destination_path}"
        logger.info("Uploaded blob to %s", uri)
        return uri
    except Exception as exc:
        logger.error("Failed to upload blob to %s: %s", destination_path, exc)
        raise


def download_blob(
    source_path: str,
    bucket_name: Optional[str] = None,
) -> bytes:
    """Download a blob from GCS.

    Args:
        source_path: The object path within the bucket.
        bucket_name: Override the default bucket name.

    Returns:
        The blob content as bytes.
    """
    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name or settings.gcs_bucket)
        blob = bucket.blob(source_path)
        data = blob.download_as_bytes()
        logger.info("Downloaded blob from gs://%s/%s", bucket.name, source_path)
        return data
    except Exception as exc:
        logger.error("Failed to download blob %s: %s", source_path, exc)
        raise


def get_signed_url(
    source_path: str,
    expiration_minutes: int = 60,
    bucket_name: Optional[str] = None,
) -> str:
    """Generate a signed URL for a GCS object.

    Args:
        source_path: The object path within the bucket.
        expiration_minutes: How long the URL remains valid.
        bucket_name: Override the default bucket name.

    Returns:
        A signed URL string.
    """
    import datetime

    try:
        client = get_storage_client()
        bucket = client.bucket(bucket_name or settings.gcs_bucket)
        blob = bucket.blob(source_path)
        url = blob.generate_signed_url(
            expiration=datetime.timedelta(minutes=expiration_minutes),
            method="GET",
        )
        logger.info("Generated signed URL for %s", source_path)
        return url
    except Exception as exc:
        logger.error("Failed to generate signed URL for %s: %s", source_path, exc)
        raise
