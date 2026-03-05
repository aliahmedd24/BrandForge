"""Image Generator tool implementations — Phase 2.

Generates production-quality images via Imagen 4.0 Ultra for every
platform spec, with 3 A/B/C variants per spec for A/B testing.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_ASSETS,
    FIRESTORE_COLLECTION_BRAND_DNA,
    FIRESTORE_COLLECTION_MOOD_BOARDS,
    IMAGEN_MODEL,
    MAX_RETRIES,
    PLATFORM_IMAGE_SPECS,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    RETRY_BASE_DELAY_SECONDS,
    EVENT_IMAGEGEN_COMPLETE,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    GeneratedImage,
    ImageSpec,
    Platform,
)
from brandforge.shared.utils import retry_with_backoff

logger = logging.getLogger(__name__)

_MAX_PROMPT_TOKENS = 480
_VARIANTS = 3


# ---------------------------------------------------------------------------
# Tool: generate_platform_images
# ---------------------------------------------------------------------------


async def generate_platform_images(
    campaign_id: str,
    brand_dna_id: str,
    platforms_json: str,
    mood_board_urls_json: str = "[]",
) -> dict[str, Any]:
    """Generate production images for all platform specs.

    For each platform, looks up its ImageSpec list, and generates 3 variants
    (A/B/C) per spec via Imagen 4.0 Ultra. All prompts are grounded in BrandDNA.

    Args:
        campaign_id: The campaign ID.
        brand_dna_id: The BrandDNA document ID.
        platforms_json: JSON array of platform strings.
        mood_board_urls_json: Optional JSON array of mood board GCS URLs.

    Returns:
        dict with status and list of GeneratedImage dicts.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.storage import upload_blob

        brand_dna_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            doc_id=brand_dna_id,
        )
        if not brand_dna_data:
            return {"status": "error", "error": f"BrandDNA {brand_dna_id} not found."}

        platforms = json.loads(platforms_json) if isinstance(platforms_json, str) else platforms_json
        brand_dna_version = brand_dna_data.get("version", 1)

        all_images: list[dict[str, Any]] = []
        errors: list[str] = []

        config = get_config()

        for platform_str in platforms:
            specs_raw = PLATFORM_IMAGE_SPECS.get(platform_str, [])
            if not specs_raw:
                logger.warning("No image specs for platform: %s", platform_str)
                continue

            for spec_dict in specs_raw:
                spec = ImageSpec(platform=Platform(platform_str), **spec_dict)

                for variant_num in range(1, _VARIANTS + 1):
                    try:
                        prompt = _build_imagen_prompt(
                            brand_dna_data=brand_dna_data,
                            spec=spec,
                            variant_number=variant_num,
                        )

                        # Truncate prompt if needed
                        if len(prompt) > _MAX_PROMPT_TOKENS * 4:
                            prompt = prompt[: _MAX_PROMPT_TOKENS * 4]
                            logger.warning("Prompt truncated for %s variant %d", platform_str, variant_num)

                        async def _call_imagen(p: str = prompt) -> bytes:
                            from google.cloud import aiplatform
                            from vertexai.preview.vision_models import ImageGenerationModel
                            import asyncio

                            model = ImageGenerationModel.from_pretrained(IMAGEN_MODEL)
                            response = await asyncio.to_thread(
                                model.generate_images,
                                prompt=p,
                                number_of_images=1,
                                aspect_ratio=spec.aspect_ratio.replace(":", ":"),
                            )
                            return response.images[0]._image_bytes

                        image_bytes = await retry_with_backoff(
                            _call_imagen,
                            max_retries=MAX_RETRIES,
                            base_delay=RETRY_BASE_DELAY_SECONDS,
                            operation_name=f"imagen_{platform_str}_{spec.use_case}_v{variant_num}",
                        )

                        gcs_path = (
                            f"campaigns/{campaign_id}/images/{platform_str}/"
                            f"{spec.use_case}_{spec.width}x{spec.height}_v{variant_num}.png"
                        )
                        gcs_url = await upload_blob(
                            destination_path=gcs_path,
                            data=image_bytes,
                            content_type="image/png",
                        )

                        img = GeneratedImage(
                            campaign_id=campaign_id,
                            platform=Platform(platform_str),
                            spec=spec,
                            gcs_url=gcs_url,
                            variant_number=variant_num,
                            generation_prompt=prompt,
                            brand_dna_version=brand_dna_version,
                        )
                        all_images.append(img.model_dump(mode="json"))

                    except Exception as exc:
                        msg = f"{platform_str}/{spec.use_case}/v{variant_num}: {exc}"
                        logger.error("Image generation failed: %s", msg)
                        errors.append(msg)

        if not all_images:
            return {"status": "error", "error": f"All image generations failed: {errors}"}

        result: dict[str, Any] = {
            "status": "success",
            "data": all_images,
            "image_count": len(all_images),
        }
        if errors:
            result["partial_errors"] = errors

        logger.info("Generated %d images for campaign %s", len(all_images), campaign_id)
        return result

    except Exception as exc:
        logger.error("generate_platform_images failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: store_generated_images
# ---------------------------------------------------------------------------


async def store_generated_images(
    images_json: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Batch store GeneratedImage records in Firestore + publish completion.

    Args:
        images_json: JSON array of GeneratedImage dicts.
        campaign_id: The campaign ID.

    Returns:
        dict with status and image IDs.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message

        images_data = json.loads(images_json) if isinstance(images_json, str) else images_json
        if isinstance(images_data, dict):
            images_data = [images_data]

        image_ids: list[str] = []
        for img_dict in images_data:
            img = GeneratedImage(**img_dict)
            await fs.create_document(
                collection=FIRESTORE_COLLECTION_ASSETS,
                doc_id=img.id,
                data=img.model_dump(mode="json"),
            )
            image_ids.append(img.id)

        # AgentRun record
        agent_run = AgentRun(
            campaign_id=campaign_id,
            agent_name="image_generator",
            status=AgentStatus.COMPLETE,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            output_ref=f"campaigns/{campaign_id}/images/",
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
                source_agent="image_generator",
                target_agent="orchestrator",
                campaign_id=campaign_id,
                event_type=EVENT_IMAGEGEN_COMPLETE,
                payload={"image_ids": image_ids, "image_count": len(image_ids)},
            ),
        )

        logger.info("Stored %d images for campaign %s", len(image_ids), campaign_id)
        return {"status": "success", "image_ids": image_ids, "image_count": len(image_ids)}

    except Exception as exc:
        logger.error("store_generated_images failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_imagen_prompt(
    brand_dna_data: dict[str, Any],
    spec: ImageSpec,
    variant_number: int,
) -> str:
    """Build an Imagen prompt grounded in BrandDNA for a specific variant."""
    brand_name = brand_dna_data.get("brand_name", "")
    visual_dir = brand_dna_data.get("visual_direction", "")
    personality = ", ".join(brand_dna_data.get("brand_personality", []))
    palette = brand_dna_data.get("color_palette", {})

    variant_focus = {
        1: "Hero composition — primary product/brand focus, clean and impactful",
        2: "Lifestyle context — product in use, real-world environment, relatable",
        3: "Abstract/emotional — brand mood and feeling, artistic interpretation",
    }.get(variant_number, "Standard composition")

    return (
        f"Create a production-quality advertising image for {brand_name}.\n"
        f"Platform: {spec.platform}, Use case: {spec.use_case}\n"
        f"Dimensions: {spec.width}x{spec.height}, Aspect ratio: {spec.aspect_ratio}\n"
        f"Brand personality: {personality}\n"
        f"Visual direction: {visual_dir}\n"
        f"Color palette: primary {palette.get('primary','')}, "
        f"secondary {palette.get('secondary','')}, accent {palette.get('accent','')}\n"
        f"Variant focus: {variant_focus}\n"
        f"Style: Professional advertising photography, high production value, "
        f"brand-consistent color grading."
    )
