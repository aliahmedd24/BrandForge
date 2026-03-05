"""Virtual Try-On tool implementations — Phase 2.

Generates virtual garment try-on images via virtual-try-on-001 for
fashion/clothing brands. Gracefully skips non-fashion brands.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_BRAND_DNA,
    MAX_RETRIES,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    RETRY_BASE_DELAY_SECONDS,
    TRYON_MODEL,
    EVENT_TRYON_COMPLETE,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    GeneratedTryOn,
)
from brandforge.shared.utils import retry_with_backoff

logger = logging.getLogger(__name__)

_FASHION_KEYWORDS = [
    "clothing", "apparel", "fashion", "garment", "wear", "dress",
    "shirt", "jacket", "pants", "shoes", "accessories", "textile",
    "outfit", "wardrobe", "couture", "streetwear", "athleisure",
]


# ---------------------------------------------------------------------------
# Tool: generate_tryon_images
# ---------------------------------------------------------------------------


async def generate_tryon_images(
    campaign_id: str,
    brand_dna_id: str,
    product_image_gcs: str,
    model_image_gcs: str,
    num_variants: int = 3,
) -> dict[str, Any]:
    """Generate virtual try-on images.

    Checks if the brand is fashion-related. If yes, calls virtual-try-on-001
    to generate variants. If not, returns empty results gracefully.

    Args:
        campaign_id: The campaign ID.
        brand_dna_id: The BrandDNA document ID.
        product_image_gcs: GCS URL of the product garment image.
        model_image_gcs: GCS URL of the model reference image.
        num_variants: Number of variants to generate (default 3).

    Returns:
        dict with status and list of GeneratedTryOn dicts.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.storage import download_blob, upload_blob
        from brandforge.shared.utils import gcs_uri_to_blob_path

        # Fetch BrandDNA
        brand_dna_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            doc_id=brand_dna_id,
        )
        if not brand_dna_data:
            return {"status": "error", "error": f"BrandDNA {brand_dna_id} not found."}

        # Fashion brand check
        product_desc = brand_dna_data.get("product_description", "").lower()
        brand_essence = brand_dna_data.get("brand_essence", "").lower()
        combined_text = f"{product_desc} {brand_essence}"

        is_fashion = any(kw in combined_text for kw in _FASHION_KEYWORDS)
        if not is_fashion:
            logger.info(
                "Brand is not fashion-related — skipping try-on for campaign %s",
                campaign_id,
            )
            return {
                "status": "success",
                "data": [],
                "message": "Brand is not fashion-related. Try-on skipped gracefully.",
                "skipped": True,
            }

        config = get_config()

        # Validate images exist
        product_blob = gcs_uri_to_blob_path(product_image_gcs)
        model_blob = gcs_uri_to_blob_path(model_image_gcs)
        product_bytes = await download_blob(product_blob)
        model_bytes = await download_blob(model_blob)

        results: list[dict[str, Any]] = []
        errors: list[str] = []

        for variant in range(1, num_variants + 1):
            try:
                async def _call_tryon(v: int = variant) -> bytes:
                    from google.cloud import aiplatform
                    import asyncio

                    client = aiplatform.gapic.PredictionServiceClient(
                        client_options={
                            "api_endpoint": f"{config.gcp_region}-aiplatform.googleapis.com"
                        }
                    )

                    import base64
                    endpoint = (
                        f"projects/{config.gcp_project_id}/locations/{config.gcp_region}/"
                        f"publishers/google/models/{TRYON_MODEL}"
                    )

                    response = await asyncio.to_thread(
                        client.predict,
                        endpoint=endpoint,
                        instances=[{
                            "productImage": base64.b64encode(product_bytes).decode("utf-8"),
                            "modelImage": base64.b64encode(model_bytes).decode("utf-8"),
                        }],
                    )

                    # Extract generated image bytes
                    prediction = response.predictions[0]
                    img_b64 = str(prediction.get("generatedImage", ""))
                    return base64.b64decode(img_b64)

                image_bytes = await retry_with_backoff(
                    _call_tryon,
                    max_retries=MAX_RETRIES,
                    base_delay=RETRY_BASE_DELAY_SECONDS,
                    operation_name=f"tryon_v{variant}",
                )

                gcs_path = f"campaigns/{campaign_id}/tryon/variant_{variant}.png"
                gcs_url = await upload_blob(
                    destination_path=gcs_path,
                    data=image_bytes,
                    content_type="image/png",
                )

                tryon = GeneratedTryOn(
                    campaign_id=campaign_id,
                    product_image_gcs=product_image_gcs,
                    model_image_gcs=model_image_gcs,
                    gcs_url=gcs_url,
                    variant_number=variant,
                )
                results.append(tryon.model_dump(mode="json"))

            except Exception as exc:
                msg = f"variant {variant}: {exc}"
                logger.error("Try-on generation failed: %s", msg)
                errors.append(msg)

        if not results:
            return {"status": "error", "error": f"All try-on generations failed: {errors}"}

        result: dict[str, Any] = {
            "status": "success",
            "data": results,
            "variant_count": len(results),
        }
        if errors:
            result["partial_errors"] = errors

        logger.info("Generated %d try-on variants for campaign %s", len(results), campaign_id)
        return result

    except Exception as exc:
        logger.error("generate_tryon_images failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: store_tryon_results
# ---------------------------------------------------------------------------


async def store_tryon_results(
    tryon_json: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Persist GeneratedTryOn records to Firestore + publish completion.

    Args:
        tryon_json: JSON array of GeneratedTryOn dicts.
        campaign_id: The campaign ID.

    Returns:
        dict with status and try-on IDs.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message

        tryon_data = json.loads(tryon_json) if isinstance(tryon_json, str) else tryon_json
        if isinstance(tryon_data, dict):
            tryon_data = [tryon_data]

        tryon_ids: list[str] = []
        for td in tryon_data:
            tryon = GeneratedTryOn(**td)
            await fs.create_document(
                collection="generated_tryons",
                doc_id=tryon.id,
                data=tryon.model_dump(mode="json"),
            )
            tryon_ids.append(tryon.id)

        # AgentRun
        agent_run = AgentRun(
            campaign_id=campaign_id,
            agent_name="virtual_tryon",
            status=AgentStatus.COMPLETE,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            output_ref=f"campaigns/{campaign_id}/tryon/",
        )
        await fs.create_document(
            collection="agent_runs",
            doc_id=agent_run.id,
            data=agent_run.model_dump(mode="json"),
        )

        # Publish completion
        await publish_message(
            topic=PUBSUB_TOPIC_AGENT_COMPLETE,
            message=AgentMessage(
                source_agent="virtual_tryon",
                target_agent="orchestrator",
                campaign_id=campaign_id,
                event_type=EVENT_TRYON_COMPLETE,
                payload={"tryon_ids": tryon_ids, "variant_count": len(tryon_ids)},
            ),
        )

        logger.info("Stored %d try-on results for campaign %s", len(tryon_ids), campaign_id)
        return {"status": "success", "tryon_ids": tryon_ids, "variant_count": len(tryon_ids)}

    except Exception as exc:
        logger.error("store_tryon_results failed: %s", exc)
        return {"status": "error", "error": str(exc)}
