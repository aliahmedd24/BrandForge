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

# Phase 2: Creative Production collections
FIRESTORE_COLLECTION_SCRIPTS = "scripts"
FIRESTORE_COLLECTION_ASSETS = "assets"
FIRESTORE_COLLECTION_COPY_PACKAGES = "copy_packages"
FIRESTORE_COLLECTION_MOOD_BOARDS = "mood_boards"

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

# Phase 2: Agent completion event types (all published to PUBSUB_TOPIC_AGENT_COMPLETE)
EVENT_SCRIPTWRITER_COMPLETE = "scriptwriter_complete"
EVENT_MOODBOARD_COMPLETE = "mood_board_complete"
EVENT_IMAGEGEN_COMPLETE = "image_generator_complete"
EVENT_VIDEOPRODUCER_COMPLETE = "video_producer_complete"
EVENT_COPYEDITOR_COMPLETE = "copy_editor_complete"
EVENT_TRYON_COMPLETE = "virtual_tryon_complete"
EVENT_PRODUCTION_COMPLETE = "production_complete"

GCS_BUCKET_NAME = "brandforge-assets"
GCP_REGION = "us-central1"

# Phase 2: Model identifiers
IMAGEN_MODEL = "imagen-4.0-ultra-generate-001"
VEO_MODEL = "veo-3.1-generate-preview"
TRYON_MODEL = "virtual-try-on-001"
IMAGE_PREVIEW_MODEL = "gemini-3-pro-image-preview"

# Phase 2: Veo polling configuration
VEO_POLL_INTERVAL_SECONDS = 30
VEO_MAX_TIMEOUT_SECONDS = 600

# Phase 2: Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 4

# Phase 2: Platform image specs — dimensions per platform per PRD table
# Values are dicts; convert to ImageSpec at runtime to avoid circular imports.
PLATFORM_IMAGE_SPECS: dict[str, list[dict[str, str | int]]] = {
    "instagram": [
        {"width": 1080, "height": 1080, "aspect_ratio": "1:1", "use_case": "feed_post"},
        {"width": 1080, "height": 1920, "aspect_ratio": "9:16", "use_case": "story"},
    ],
    "linkedin": [
        {"width": 1200, "height": 627, "aspect_ratio": "16:9", "use_case": "feed_post"},
    ],
    "twitter_x": [
        {"width": 1600, "height": 900, "aspect_ratio": "16:9", "use_case": "feed_post"},
    ],
    "facebook": [
        {"width": 1080, "height": 1080, "aspect_ratio": "1:1", "use_case": "feed_post"},
        {"width": 1200, "height": 630, "aspect_ratio": "16:9", "use_case": "banner"},
    ],
    "tiktok": [
        {"width": 1080, "height": 1920, "aspect_ratio": "9:16", "use_case": "feed_post"},
    ],
    "youtube": [
        {"width": 1280, "height": 720, "aspect_ratio": "16:9", "use_case": "thumbnail"},
    ],
}


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
