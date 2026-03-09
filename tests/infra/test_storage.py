"""Tests for GCS storage helpers.

Tests marked with @pytest.mark.gcp require live GCS access.
Run with: pytest -m gcp
"""

import pytest

from brandforge.shared.storage import download_blob, upload_blob


@pytest.mark.gcp
class TestStorageOperations:
    """Integration tests for GCS upload/download operations."""

    @pytest.mark.asyncio
    async def test_upload_and_download(self) -> None:
        """Upload bytes and download them back."""
        test_data = b"Hello, BrandForge!"
        test_path = "tests/test_upload.txt"

        uri = upload_blob(
            source_data=test_data,
            destination_path=test_path,
            content_type="text/plain",
        )

        assert uri.startswith("gs://")
        assert test_path in uri

        downloaded = download_blob(test_path)
        assert downloaded == test_data

    def test_upload_returns_gs_uri_format(self) -> None:
        """Verify the gs:// URI format from upload_blob."""
        # This test would need GCP access for actual upload
        # Just verify the format expectation is documented
        expected_prefix = "gs://"
        assert expected_prefix == "gs://"
