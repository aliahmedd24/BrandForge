"""BrandForge Pub/Sub client — publish helpers for A2A messaging.

All inter-agent communication goes through Pub/Sub. Topic names come
from config.py — never hardcode topic strings elsewhere.
"""

from __future__ import annotations

import json
import logging

from google.cloud import pubsub_v1  # type: ignore[import-untyped]

from brandforge.shared.config import get_config
from brandforge.shared.models import AgentMessage

logger = logging.getLogger(__name__)

_publisher: pubsub_v1.PublisherClient | None = None


def get_publisher_client() -> pubsub_v1.PublisherClient:
    """Return the Pub/Sub publisher client singleton.

    Returns:
        A PublisherClient instance.
    """
    global _publisher  # noqa: PLW0603
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
        logger.info("Pub/Sub publisher client initialized")
    return _publisher


def _topic_path(topic_name: str) -> str:
    """Build the full Pub/Sub topic path.

    Args:
        topic_name: Short topic name (e.g. 'brandforge.campaign.created').

    Returns:
        Full topic path: 'projects/{project}/topics/{topic}'.
    """
    config = get_config()
    publisher = get_publisher_client()
    return publisher.topic_path(config.gcp_project_id, topic_name)


async def publish_message(topic: str, message: AgentMessage) -> str:
    """Serialize and publish an AgentMessage to a Pub/Sub topic.

    Args:
        topic: The topic name (use constants from config.py).
        message: The AgentMessage to publish.

    Returns:
        The published message ID.

    Raises:
        Exception: If publishing fails after internal retries.
    """
    publisher = get_publisher_client()
    topic_path = _topic_path(topic)

    data = json.dumps(message.model_dump(mode="json")).encode("utf-8")

    future = publisher.publish(
        topic_path,
        data=data,
        source_agent=message.source_agent,
        event_type=message.event_type,
        campaign_id=message.campaign_id,
    )
    message_id: str = future.result(timeout=30)
    logger.info(
        "Published message %s to %s (event=%s, campaign=%s)",
        message_id,
        topic,
        message.event_type,
        message.campaign_id,
    )
    return message_id
