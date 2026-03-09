"""Firestore client singleton and document helpers for BrandForge.

All Firestore operations should go through this module to ensure
consistent client reuse and collection naming.
"""

import logging
from typing import Any, Optional

from google.cloud.firestore_v1 import AsyncClient, async_query

from .config import settings

logger = logging.getLogger(__name__)

# ── Collection name constants ────────────────────────────────────────────

CAMPAIGNS_COLLECTION = "campaigns"
AGENT_RUNS_SUBCOLLECTION = "agent_runs"
BRAND_DNA_COLLECTION = "brand_dna"
ASSET_BUNDLES_COLLECTION = "asset_bundles"
BRANDS_COLLECTION = "brands"

# ── Client singleton ────────────────────────────────────────────────────

_client: Optional[AsyncClient] = None


def get_firestore_client() -> AsyncClient:
    """Return the Firestore async client singleton.

    Returns:
        An AsyncClient instance connected to the configured database.
    """
    global _client
    if _client is None:
        _client = AsyncClient(
            project=settings.gcp_project or None,
            database=settings.firestore_database,
        )
        logger.info("Firestore AsyncClient initialized (db=%s)", settings.firestore_database)
    return _client


# ── Document helpers ─────────────────────────────────────────────────────


async def save_document(
    collection: str, doc_id: str, data: dict[str, Any]
) -> None:
    """Create or overwrite a document in Firestore.

    Args:
        collection: The top-level collection name.
        doc_id: The document ID.
        data: The document data as a dictionary.
    """
    try:
        client = get_firestore_client()
        await client.collection(collection).document(doc_id).set(data)
        logger.info("Saved document %s/%s", collection, doc_id)
    except Exception as exc:
        logger.error("Failed to save %s/%s: %s", collection, doc_id, exc)
        raise


async def get_document(
    collection: str, doc_id: str
) -> Optional[dict[str, Any]]:
    """Retrieve a document from Firestore.

    Args:
        collection: The top-level collection name.
        doc_id: The document ID.

    Returns:
        The document data as a dict, or None if not found.
    """
    try:
        client = get_firestore_client()
        doc = await client.collection(collection).document(doc_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as exc:
        logger.error("Failed to get %s/%s: %s", collection, doc_id, exc)
        raise


async def update_document(
    collection: str, doc_id: str, updates: dict[str, Any]
) -> None:
    """Update specific fields of a Firestore document.

    Args:
        collection: The top-level collection name.
        doc_id: The document ID.
        updates: A dict of field names to new values.
    """
    try:
        client = get_firestore_client()
        await client.collection(collection).document(doc_id).update(updates)
        logger.info("Updated document %s/%s", collection, doc_id)
    except Exception as exc:
        logger.error("Failed to update %s/%s: %s", collection, doc_id, exc)
        raise


async def query_documents(
    collection: str,
    field: str,
    value: Any,
    order_by: Optional[str] = None,
    descending: bool = True,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Query Firestore documents where a field equals a value.

    Args:
        collection: The top-level collection name.
        field: The field name to filter on.
        value: The value to match.
        order_by: Optional field to order results by.
        descending: Sort descending if True, ascending if False.
        limit: Maximum number of documents to return.

    Returns:
        A list of document data dicts.
    """
    try:
        client = get_firestore_client()
        query = client.collection(collection).where(
            filter=async_query.FieldFilter(field, "==", value)
        )
        if order_by:
            direction = (
                async_query.Query.DESCENDING
                if descending
                else async_query.Query.ASCENDING
            )
            query = query.order_by(order_by, direction=direction)
        query = query.limit(limit)
        docs = await query.get()
        return [doc.to_dict() for doc in docs]
    except Exception as exc:
        logger.error(
            "Failed to query %s where %s==%s: %s", collection, field, value, exc
        )
        raise
