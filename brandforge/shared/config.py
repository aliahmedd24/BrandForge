"""Configuration and secrets management for BrandForge.

Loads settings from environment variables (with BRANDFORGE_ prefix) and
falls back to Google Secret Manager in production environments.
"""

import logging
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class BrandForgeConfig(BaseSettings):
    """Application settings loaded from environment variables.

    All env vars are prefixed with BRANDFORGE_ (e.g. BRANDFORGE_GCS_BUCKET).
    For local development, place values in a .env file.
    """

    # GCP core
    gcp_project: str = ""
    gcp_region: str = "us-central1"

    # Google Cloud Storage
    gcs_bucket: str = "brandforge-assets"

    # Firestore
    firestore_database: str = "(default)"

    # Pub/Sub topic names
    pubsub_campaign_created_topic: str = "brandforge.campaign.created"
    pubsub_campaign_published_topic: str = "brandforge.campaign.published"

    # Artifact Registry
    ar_repo: str = "brandforge-repo"

    model_config = {
        "env_prefix": "BRANDFORGE_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def load_secret(secret_id: str, project: Optional[str] = None) -> str:
    """Load a secret from Google Secret Manager, falling back to env vars.

    Args:
        secret_id: The secret name in Secret Manager (e.g. "GEMINI_API_KEY").
        project: GCP project ID. Defaults to settings.gcp_project.

    Returns:
        The secret value as a string.

    Raises:
        RuntimeError: If the secret cannot be loaded from any source.
    """
    import os

    # Try environment variable first (for local dev)
    env_value = os.environ.get(secret_id) or os.environ.get(secret_id.upper())
    if env_value:
        logger.debug("Loaded secret %s from environment", secret_id)
        return env_value

    # Fall back to Secret Manager
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        project_id = project or settings.gcp_project
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        logger.info("Loaded secret %s from Secret Manager", secret_id)
        return response.payload.data.decode("utf-8")
    except Exception as exc:
        logger.error("Failed to load secret %s: %s", secret_id, exc)
        raise RuntimeError(
            f"Cannot load secret '{secret_id}' from env or Secret Manager"
        ) from exc


def get_vertexai_config() -> dict[str, str]:
    """Return Vertex AI configuration for google.genai Client.

    Returns:
        A dict with 'project' and 'location' keys for Vertex AI.
    """
    return {
        "project": settings.gcp_project,
        "location": settings.gcp_region,
    }


@lru_cache(maxsize=1)
def _get_settings() -> BrandForgeConfig:
    """Create and cache the singleton settings instance."""
    return BrandForgeConfig()


settings: BrandForgeConfig = _get_settings()
