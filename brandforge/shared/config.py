"""BrandForge configuration — loads secrets and project-wide settings.

Production: secrets from Google Secret Manager.
Local dev: secrets from .env.local via python-dotenv.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — collection names, topic names, bucket names
# ---------------------------------------------------------------------------

FIRESTORE_COLLECTION_CAMPAIGNS = "campaigns"
FIRESTORE_COLLECTION_BRAND_DNA = "brand_dna"
FIRESTORE_COLLECTION_ASSET_BUNDLES = "asset_bundles"
FIRESTORE_COLLECTION_BRANDS = "brands"
FIRESTORE_SUBCOLLECTION_AGENT_RUNS = "agent_runs"

PUBSUB_TOPIC_CAMPAIGN_CREATED = "brandforge.campaign.created"
PUBSUB_TOPIC_AGENT_COMPLETE = "brandforge.agent.complete"
PUBSUB_TOPIC_QA_FAILED = "brandforge.qa.failed"
PUBSUB_TOPIC_CAMPAIGN_PUBLISHED = "brandforge.campaign.published"
PUBSUB_TOPIC_ANALYTICS_INSIGHTS = "brandforge.analytics.insights"

ALL_PUBSUB_TOPICS = [
    PUBSUB_TOPIC_CAMPAIGN_CREATED,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    PUBSUB_TOPIC_QA_FAILED,
    PUBSUB_TOPIC_CAMPAIGN_PUBLISHED,
    PUBSUB_TOPIC_ANALYTICS_INSIGHTS,
]

GCS_BUCKET_NAME = "brandforge-assets"
GCP_REGION = "us-central1"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrandForgeConfig:
    """Immutable project-wide configuration."""

    gcp_project_id: str
    gcp_region: str = GCP_REGION
    gcs_bucket_name: str = GCS_BUCKET_NAME
    gemini_model: str = "gemini-3.1-pro-preview"
    pubsub_topics: list[str] = field(default_factory=lambda: list(ALL_PUBSUB_TOPICS))


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

_env_loaded = False


def _ensure_env_loaded() -> None:
    """Load .env.local for local development if it exists."""
    global _env_loaded  # noqa: PLW0603
    if _env_loaded:
        return
    root = Path(__file__).resolve().parents[2]
    for env_name in (".env", ".env.local"):
        env_path = root / env_name
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("Loaded environment from %s", env_path)
            break
    _env_loaded = True


# ---------------------------------------------------------------------------
# Secret access
# ---------------------------------------------------------------------------


async def get_secret(name: str) -> str:
    """Retrieve a secret value.

    In production (when SECRET_MANAGER_ENABLED=true), fetches from Google
    Secret Manager. Otherwise falls back to environment variables loaded
    from .env.local.

    Args:
        name: The secret name (e.g. 'GEMINI_API_KEY').

    Returns:
        The secret value as a string.

    Raises:
        ValueError: If the secret cannot be found in any source.
    """
    _ensure_env_loaded()

    # Fast path — environment variable (local dev)
    env_value = os.getenv(name)
    if env_value:
        return env_value

    # Production path — Secret Manager
    if os.getenv("SECRET_MANAGER_ENABLED", "").lower() == "true":
        return await _get_secret_from_manager(name)

    raise ValueError(
        f"Secret '{name}' not found. Set it in .env.local or enable Secret Manager."
    )


async def _get_secret_from_manager(name: str) -> str:
    """Fetch a secret from Google Secret Manager.

    Args:
        name: The secret name.

    Returns:
        The secret value string.

    Raises:
        ValueError: If the secret does not exist or has no versions.
    """
    from google.cloud import secretmanager  # type: ignore[import-untyped]

    project_id = os.getenv("GCP_PROJECT_ID", "brandforge-489114")
    client = secretmanager.SecretManagerServiceClient()
    resource_name = f"projects/{project_id}/secrets/{name}/versions/latest"

    try:
        response = client.access_secret_version(request={"name": resource_name})
        return response.payload.data.decode("UTF-8")
    except Exception as exc:
        logger.error("Failed to access secret '%s': %s", name, exc)
        raise ValueError(f"Secret '{name}' not accessible in Secret Manager.") from exc


# ---------------------------------------------------------------------------
# Config singleton
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_config() -> BrandForgeConfig:
    """Return the project-wide configuration singleton.

    Returns:
        A frozen BrandForgeConfig instance.
    """
    _ensure_env_loaded()
    return BrandForgeConfig(
        gcp_project_id=os.getenv("GCP_PROJECT_ID", "brandforge-489114"),
        gcp_region=os.getenv("GCP_REGION", GCP_REGION),
        gcs_bucket_name=os.getenv("GCS_BUCKET_NAME", GCS_BUCKET_NAME),
    )
