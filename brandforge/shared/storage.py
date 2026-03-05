"""BrandForge GCS (Cloud Storage) client — singleton + helpers.

All file asset access goes through this module. Bucket name comes from
config.py — never hardcode bucket strings elsewhere.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from google.cloud import storage  # type: ignore[import-untyped]

from brandforge.shared.config import get_config

logger = logging.getLogger(__name__)

_client: storage.Client | None = None


def get_storage_client() -> storage.Client:
    """Return the GCS client singleton.

    Returns:
        A storage.Client instance connected to the project.
    """
    global _client  # noqa: PLW0603
    if _client is None:
        config = get_config()
        _client = storage.Client(project=config.gcp_project_id)
        logger.info("GCS client initialized for project %s", config.gcp_project_id)
    return _client


def _get_bucket() -> storage.Bucket:
    """Return the default assets bucket.

    Returns:
        The GCS Bucket object for brandforge-assets.
    """
    config = get_config()
    return get_storage_client().bucket(config.gcs_bucket_name)


async def upload_blob(
    destination_path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload bytes to the assets bucket.

    Args:
        destination_path: The GCS object path (e.g. 'campaigns/{id}/brief/voice.webm').
        data: The raw bytes to upload.
        content_type: MIME type of the data.

    Returns:
        The full gs:// URI of the uploaded object.
    """
    bucket = _get_bucket()
    blob = bucket.blob(destination_path)
    blob.upload_from_string(data, content_type=content_type)
    uri = f"gs://{bucket.name}/{destination_path}"
    logger.info("Uploaded blob: %s (%d bytes)", uri, len(data))
    return uri


async def download_blob(source_path: str) -> bytes:
    """Download a blob from the assets bucket.

    Args:
        source_path: The GCS object path.

    Returns:
        The raw bytes of the object.

    Raises:
        ValueError: If the object does not exist.
    """
    bucket = _get_bucket()
    blob = bucket.blob(source_path)
    if not blob.exists():
        raise ValueError(f"Blob not found: gs://{bucket.name}/{source_path}")
    data: bytes = blob.download_as_bytes()
    logger.info("Downloaded blob: gs://%s/%s (%d bytes)", bucket.name, source_path, len(data))
    return data


async def generate_signed_url(
    blob_path: str,
    expiration_minutes: int = 60,
) -> str:
    """Generate a signed URL for private blob access.

    Args:
        blob_path: The GCS object path.
        expiration_minutes: How long the URL stays valid.

    Returns:
        A signed HTTPS URL.
    """
    bucket = _get_bucket()
    blob = bucket.blob(blob_path)
    url: str = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiration_minutes),
        method="GET",
    )
    logger.info("Generated signed URL for %s (expires in %d min)", blob_path, expiration_minutes)
    return url


async def delete_blob(blob_path: str) -> None:
    """Delete a blob from the assets bucket.

    Args:
        blob_path: The GCS object path to delete.
    """
    bucket = _get_bucket()
    blob = bucket.blob(blob_path)
    blob.delete()
    logger.info("Deleted blob: gs://%s/%s", bucket.name, blob_path)
