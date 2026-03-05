"""Tests for GCS (Cloud Storage) connectivity and operations.

These tests require a live GCS bucket. They will be marked
[UNVERIFIED] if GCP is not configured.
"""

from __future__ import annotations

import uuid

import pytest

from brandforge.shared.storage import (
    delete_blob,
    download_blob,
    upload_blob,
)


@pytest.mark.asyncio
async def test_storage_upload_and_download() -> None:
    """Can upload and download a file from the assets bucket."""
    test_path = f"tests/test-{uuid.uuid4()}.txt"
    test_data = b"BrandForge storage integration test"

    # Upload
    uri = await upload_blob(test_path, test_data, content_type="text/plain")
    assert uri.startswith("gs://")
    assert test_path in uri

    # Download
    downloaded = await download_blob(test_path)
    assert downloaded == test_data

    # Cleanup
    await delete_blob(test_path)


@pytest.mark.asyncio
async def test_storage_download_nonexistent_raises() -> None:
    """Downloading a blob that doesn't exist should raise ValueError."""
    fake_path = f"tests/nonexistent-{uuid.uuid4()}.txt"
    with pytest.raises(ValueError, match="Blob not found"):
        await download_blob(fake_path)
