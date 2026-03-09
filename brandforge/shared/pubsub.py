"""Google Cloud Pub/Sub publisher helpers for BrandForge.

Pub/Sub is used exclusively for external event triggers:
  - brandforge.campaign.created (API/Frontend → Orchestrator)
  - brandforge.campaign.published (Distribution Agent → Cloud Scheduler)

All agent-to-agent communication uses native ADK A2A instead.
"""

import json
import logging
from typing import Any, Optional

from google.cloud import pubsub_v1

from .config import settings

logger = logging.getLogger(__name__)

# ── Client singleton ────────────────────────────────────────────────────

_publisher: Optional[pubsub_v1.PublisherClient] = None


def get_publisher() -> pubsub_v1.PublisherClient:
    """Return the Pub/Sub publisher client singleton.

    Returns:
        A PublisherClient instance.
    """
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
        logger.info("Pub/Sub PublisherClient initialized")
    return _publisher


# ── Publishing ───────────────────────────────────────────────────────────


def publish_message(
    topic_name: str,
    data: dict[str, Any],
    project: Optional[str] = None,
    **attributes: str,
) -> str:
    """Publish a JSON message to a Pub/Sub topic.

    Args:
        topic_name: The short topic name (e.g. "brandforge.campaign.created").
        data: The message payload, serialized to JSON.
        project: GCP project ID override. Defaults to settings.gcp_project.
        **attributes: Optional message attributes (key-value string pairs).

    Returns:
        The published message ID.
    """
    try:
        publisher = get_publisher()
        project_id = project or settings.gcp_project
        topic_path = publisher.topic_path(project_id, topic_name)
        message_bytes = json.dumps(data, default=str).encode("utf-8")
        future = publisher.publish(topic_path, data=message_bytes, **attributes)
        message_id = future.result()
        logger.info("Published message %s to %s", message_id, topic_name)
        return message_id
    except Exception as exc:
        logger.error("Failed to publish to %s: %s", topic_name, exc)
        raise
