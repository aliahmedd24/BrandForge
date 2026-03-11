
"""FunctionTool implementations for the Image Generator Agent.

Generates production-ready campaign images via Imagen 4 Ultra for all
platform specs with 3 A/B/C variants each.
"""

import asyncio
import logging
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.image_generator.prompts import (
    IMAGE_GENERATION_PROMPT_TEMPLATE,
    VARIANT_DIRECTIONS,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import GENERATED_IMAGES_COLLECTION, save_document
from brandforge.shared.models import BrandDNA, GeneratedImage, ImageSpec, Platform
from brandforge.shared.retry import retry_with_backoff
from brandforge.shared.storage import upload_blob

logger = logging.getLogger(__name__)

IMAGEN_MODEL = "imagen-4.0-ultra-generate-001"

# All platform specs — filtered at runtime to campaign platforms
ALL_PLATFORM_SPECS = [
    ImageSpec(platform=Platform.INSTAGRAM, width=1080, height=1080, aspect_ratio="1:1", use_case="feed_post"),
    ImageSpec(platform=Platform.INSTAGRAM, width=1080, height=1920, aspect_ratio="9:16", use_case="story"),
    ImageSpec(platform=Platform.LINKEDIN, width=1200, height=627, aspect_ratio="16:9", use_case="banner"),
    ImageSpec(platform=Platform.TWITTER_X, width=1600, height=900, aspect_ratio="16:9", use_case="banner"),
    ImageSpec(platform=Platform.FACEBOOK, width=1080, height=1080, aspect_ratio="1:1", use_case="feed_post"),
    ImageSpec(platform=Platform.FACEBOOK, width=1200, height=630, aspect_ratio="16:9", use_case="banner"),
]

# ── Gemini/Imagen client singleton ─────────────────────────────────────

_genai_client: Optional[genai.Client] = None


def _get_genai_client() -> genai.Client:
    """Return a cached google.genai Client configured for Vertex AI."""
    global _genai_client
    if _genai_client is None:
        config = get_vertexai_config()
        _genai_client = genai.Client(
            vertexai=True,
            project=config["project"],
            location=config["location"],
        )
    return _genai_client


# ── Tool: Generate Campaign Images ─────────────────────────────────────


async def generate_campaign_images(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Generate campaign images for all applicable platform specs.

    For each platform spec matching the campaign's platforms, generates
    3 variants (A/B/C) via Imagen 4 Ultra. Uploads each to GCS and
    creates GeneratedImage records.

    Args:
        campaign_id: The campaign to generate images for.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with total_images count and per-platform breakdown.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            logger.error("No brand_dna in session state for campaign %s", real_campaign_id)
            return {"error": "No brand_dna found in session state."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)
        client = _get_genai_client()

        # Filter specs to campaign platforms
        campaign_platforms = set(brand_dna.platform_strategy.keys())
        applicable_specs = [
            spec for spec in ALL_PLATFORM_SPECS
            if spec.platform.value in campaign_platforms
        ]

        if not applicable_specs:
            logger.warning(
                "No matching platform specs for campaign %s (platforms: %s)",
                real_campaign_id, campaign_platforms,
            )
            applicable_specs = ALL_PLATFORM_SPECS[:2]

        generated_images: list[dict] = []

        for spec in applicable_specs:
            for variant_num in range(1, 4):  # 3 variants: A, B, C
                prompt = IMAGE_GENERATION_PROMPT_TEMPLATE.format(
                    visual_direction=brand_dna.visual_direction,
                    brand_personality=", ".join(brand_dna.brand_personality),
                    primary_color=brand_dna.color_palette.primary,
                    secondary_color=brand_dna.color_palette.secondary,
                    accent_color=brand_dna.color_palette.accent,
                    persona_name=brand_dna.primary_persona.name,
                    platform=spec.platform.value,
                    use_case=spec.use_case,
                    width=spec.width,
                    height=spec.height,
                    aspect_ratio=spec.aspect_ratio,
                    variant=variant_num,
                    variant_direction=VARIANT_DIRECTIONS[variant_num],
                )
                # Truncate to under 480 tokens
                if len(prompt) > 1900:
                    prompt = prompt[:1900]

                logger.info(
                    "Generating image: %s %s variant %d for campaign %s",
                    spec.platform.value, spec.use_case, variant_num, real_campaign_id,
                )

                async def _generate(p: str) -> bytes:
                    """Call Imagen to generate a single image."""
                    response = await asyncio.to_thread(
                        client.models.generate_images,
                        model=IMAGEN_MODEL,
                        prompt=p,
                        config=types.GenerateImagesConfig(
                            number_of_images=1,
                        ),
                    )
                    if response.generated_images:
                        return response.generated_images[0].image.image_bytes
                    raise ValueError("Imagen returned no images")

                image_bytes = await retry_with_backoff(_generate, prompt)

                # Upload to GCS
                gcs_path = (
                    f"campaigns/{real_campaign_id}/production/images/"
                    f"{spec.platform.value}_{spec.use_case}_v{variant_num}.png"
                )
                gcs_uri = await asyncio.to_thread(
                    upload_blob,
                    source_data=image_bytes,
                    destination_path=gcs_path,
                    content_type="image/png",
                    metadata={"campaign_id": real_campaign_id, "agent_name": "image_generator"},
                )

                gen_image = GeneratedImage(
                    campaign_id=real_campaign_id,
                    platform=spec.platform,
                    spec=spec,
                    gcs_url=gcs_uri,
                    variant_number=variant_num,
                    generation_prompt=prompt[:500],
                    brand_dna_version=brand_dna.version,
                )

                # Save to Firestore
                await save_document(
                    GENERATED_IMAGES_COLLECTION,
                    gen_image.id,
                    gen_image.model_dump(mode="json"),
                )

                generated_images.append(gen_image.model_dump(mode="json"))

        tool_context.state["generated_images_data"] = generated_images

        logger.info(
            "Generated %d images across %d specs for campaign %s",
            len(generated_images), len(applicable_specs), real_campaign_id,
        )
        return {
            "total_images": len(generated_images),
            "specs_covered": len(applicable_specs),
            "platforms": list({img["platform"] for img in generated_images}),
        }

    except Exception as exc:
        logger.error(
            "Failed to generate campaign images for campaign %s: %s",
            real_campaign_id, exc,
        )
        return {"error": str(exc)}
