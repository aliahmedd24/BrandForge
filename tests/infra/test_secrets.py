"""Tests for Secret Manager / config loading.

test_config_loads_from_env tests local .env.local loading (no GCP needed).
test_secret_manager_access requires live Secret Manager.
"""

from __future__ import annotations

import os

import pytest

from brandforge.shared.config import get_config, get_secret


class TestConfigLocal:
    """Tests that run without GCP — purely local config."""

    def test_config_returns_project_id(self) -> None:
        """get_config() should return a config with the project ID."""
        config = get_config()
        assert config.gcp_project_id  # Should never be empty
        assert config.gcp_region  # Should default to us-central1

    def test_config_has_bucket_name(self) -> None:
        """Config should include a default bucket name."""
        config = get_config()
        assert config.gcs_bucket_name == "brandforge-assets"

    def test_config_has_pubsub_topics(self) -> None:
        """Config should include all 5 Pub/Sub topic names."""
        config = get_config()
        assert len(config.pubsub_topics) == 5
        assert "brandforge.campaign.created" in config.pubsub_topics


class TestSecretAccess:
    """Tests that may require GCP Secret Manager."""

    @pytest.mark.asyncio
    async def test_secret_from_env(self) -> None:
        """get_secret should load from environment variables."""
        os.environ["TEST_SECRET_KEY"] = "test-value-12345"  # noqa: S105
        try:
            value = await get_secret("TEST_SECRET_KEY")
            assert value == "test-value-12345"  # noqa: S105
        finally:
            del os.environ["TEST_SECRET_KEY"]

    @pytest.mark.asyncio
    async def test_secret_missing_raises(self) -> None:
        """get_secret should raise ValueError for missing secrets."""
        with pytest.raises(ValueError, match="not found"):
            await get_secret("NONEXISTENT_SECRET_KEY_999")
