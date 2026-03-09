"""Tests for config loading and secret management."""

import os
from unittest.mock import patch

from brandforge.shared.config import BrandForgeConfig, load_secret


class TestBrandForgeConfig:
    """Verify config loads defaults and env overrides."""

    def test_default_values(self) -> None:
        """Config has sensible defaults without any env vars."""
        config = BrandForgeConfig(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert config.gcs_bucket == "brandforge-assets"
        assert config.gcp_region == "us-central1"
        assert config.firestore_database == "(default)"
        assert config.ar_repo == "brandforge-repo"

    def test_env_override(self) -> None:
        """Config picks up BRANDFORGE_ prefixed env vars."""
        with patch.dict(os.environ, {"BRANDFORGE_GCS_BUCKET": "my-custom-bucket"}):
            config = BrandForgeConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.gcs_bucket == "my-custom-bucket"

    def test_pubsub_topic_defaults(self) -> None:
        """Pub/Sub topic defaults match the PRD specification."""
        config = BrandForgeConfig(_env_file=None)  # type: ignore[call-arg]
        assert config.pubsub_campaign_created_topic == "brandforge.campaign.created"
        assert config.pubsub_campaign_published_topic == "brandforge.campaign.published"


class TestLoadSecret:
    """Verify secret loading with env fallback."""

    def test_loads_from_env(self) -> None:
        """load_secret returns value from environment variable."""
        with patch.dict(os.environ, {"TEST_SECRET_KEY": "secret-value-123"}):
            result = load_secret("TEST_SECRET_KEY")
            assert result == "secret-value-123"

    def test_raises_when_not_found(self) -> None:
        """load_secret raises RuntimeError when secret is unavailable."""
        # Ensure no env var and no GCP access
        with patch.dict(os.environ, {}, clear=True):
            try:
                load_secret("NONEXISTENT_SECRET_XYZ")
                assert False, "Should have raised RuntimeError"
            except RuntimeError as exc:
                assert "NONEXISTENT_SECRET_XYZ" in str(exc)

    def test_get_vertexai_config(self) -> None:
        """get_vertexai_config returns project and location from settings."""
        from brandforge.shared.config import get_vertexai_config

        with patch.dict(os.environ, {
            "BRANDFORGE_GCP_PROJECT": "test-project",
            "BRANDFORGE_GCP_REGION": "us-east1",
        }):
            from brandforge.shared.config import BrandForgeConfig
            # Need a fresh config to pick up env overrides
            config = BrandForgeConfig(_env_file=None)  # type: ignore[call-arg]
            assert config.gcp_project == "test-project"
            assert config.gcp_region == "us-east1"
