"""BrandForge Firestore client — singleton + CRUD helpers.

All Firestore access goes through this module. Collection names come
from config.py — never hardcode collection strings elsewhere.
"""

from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore  # type: ignore[import-untyped]

from brandforge.shared.config import get_config

logger = logging.getLogger(__name__)

_client: firestore.AsyncClient | None = None


def get_firestore_client() -> firestore.AsyncClient:
    """Return the Firestore async client singleton.

    Returns:
        An AsyncClient instance connected to the project's Firestore.
    """
    global _client  # noqa: PLW0603
    if _client is None:
        config = get_config()
        _client = firestore.AsyncClient(project=config.gcp_project_id)
        logger.info("Firestore client initialized for project %s", config.gcp_project_id)
    return _client


async def create_document(
    collection: str, doc_id: str, data: dict[str, Any]
) -> str:
    """Create or overwrite a Firestore document.

    Args:
        collection: The collection name (use constants from config.py).
        doc_id: The document ID.
        data: The document data as a dict.

    Returns:
        The document ID that was written.
    """
    client = get_firestore_client()
    doc_ref = client.collection(collection).document(doc_id)
    await doc_ref.set(data)
    logger.info("Created document %s/%s", collection, doc_id)
    return doc_id


async def get_document(
    collection: str, doc_id: str
) -> dict[str, Any] | None:
    """Fetch a single Firestore document by ID.

    Args:
        collection: The collection name.
        doc_id: The document ID.

    Returns:
        The document data as a dict, or None if not found.
    """
    client = get_firestore_client()
    doc_ref = client.collection(collection).document(doc_id)
    doc = await doc_ref.get()
    if not doc.exists:
        logger.warning("Document not found: %s/%s", collection, doc_id)
        return None
    return doc.to_dict()


async def update_document(
    collection: str, doc_id: str, updates: dict[str, Any]
) -> None:
    """Merge updates into an existing Firestore document.

    Args:
        collection: The collection name.
        doc_id: The document ID.
        updates: Fields to merge into the existing document.
    """
    client = get_firestore_client()
    doc_ref = client.collection(collection).document(doc_id)
    await doc_ref.update(updates)
    logger.info("Updated document %s/%s", collection, doc_id)


async def query_collection(
    collection: str,
    field: str,
    op: str,
    value: Any,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query a collection with a single filter condition.

    Args:
        collection: The collection name.
        field: The field to filter on.
        op: Firestore comparison operator ('==', '>=', 'in', etc.).
        value: The value to compare against.
        limit: Maximum number of documents to return.

    Returns:
        A list of matching document dicts.
    """
    client = get_firestore_client()
    query = client.collection(collection).where(
        filter=firestore.FieldFilter(field, op, value)
    ).limit(limit)
    docs = []
    async for doc in query.stream():
        docs.append(doc.to_dict())
    logger.info("Queried %s where %s %s %s → %d results", collection, field, op, value, len(docs))
    return docs
