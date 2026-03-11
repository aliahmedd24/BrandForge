"""FunctionTool implementations for the Mood Board Director Agent.

Generates reference imagery via Imagen 4 Ultra and assembles a
branded PDF mood board with images, color swatches, and typography specs.
"""

import asyncio
import io
import logging
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.mood_board.prompts import MOOD_BOARD_PROMPT_TEMPLATE
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.models import BrandDNA
from brandforge.shared.retry import retry_with_backoff
from brandforge.shared.storage import download_blob, upload_blob

logger = logging.getLogger(__name__)

IMAGEN_MODEL = "imagen-4.0-ultra-generate-001"

# Scene types for the 6 mood board images
SCENE_TYPES = [
    "Hero lifestyle shot — person interacting with the product in an aspirational setting",
    "Hero lifestyle shot — environmental context showing the brand world",
    "Texture and material detail — close-up of surfaces, materials, and craftsmanship",
    "Texture and material detail — tactile elements and product quality",
    "Typography mockup — elegant text layout with brand-appropriate font styling",
    "Color palette visualization — abstract composition using the brand color palette",
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


def _gcs_path_from_url(url: str) -> str:
    """Extract the blob path from a gs:// URL.

    Returns:
        The path portion after the bucket name.
    """
    if url.startswith("gs://"):
        parts = url[5:].split("/", 1)
        return parts[1] if len(parts) > 1 else ""
    return url


# ── Tool 1: Generate Mood Board Images ─────────────────────────────────


async def generate_mood_board_images(
    campaign_id: str,
    num_images: int,
    tool_context: ToolContext,
) -> dict:
    """Generate mood board reference images via Imagen 4 Ultra.

    Creates 6 images (2x hero lifestyle, 2x texture/material, 1x typography
    mockup, 1x color palette viz). Each prompt uses Brand DNA visual direction,
    colors, and personality. Uploads to GCS and stores URIs in session state.

    Args:
        campaign_id: The campaign to generate mood board for.
        num_images: Number of images to generate (default 6).
        tool_context: ADK tool context for state access.

    Returns:
        A dict with image_count and gcs_urls list.
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

        # Use up to num_images scene types
        scenes = SCENE_TYPES[:num_images]
        gcs_urls: list[str] = []

        for i, scene_type in enumerate(scenes):
            prompt = MOOD_BOARD_PROMPT_TEMPLATE.format(
                visual_direction=brand_dna.visual_direction,
                brand_personality=", ".join(brand_dna.brand_personality),
                primary_color=brand_dna.color_palette.primary,
                secondary_color=brand_dna.color_palette.secondary,
                accent_color=brand_dna.color_palette.accent,
                font_personality=brand_dna.typography.font_personality,
                tone_summary=brand_dna.tone_of_voice[:200],
                scene_type=scene_type,
            )
            # Truncate to under 480 tokens (~1920 chars as safe estimate)
            if len(prompt) > 1900:
                prompt = prompt[:1900]

            logger.info(
                "Generating mood board image %d/%d for campaign %s",
                i + 1, len(scenes), real_campaign_id,
            )

            async def _generate_image(p: str) -> bytes:
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

            image_bytes = await retry_with_backoff(_generate_image, prompt)

            gcs_path = f"campaigns/{real_campaign_id}/production/mood_board/mood_{i}.png"
            gcs_uri = await asyncio.to_thread(
                upload_blob,
                source_data=image_bytes,
                destination_path=gcs_path,
                content_type="image/png",
                metadata={"campaign_id": real_campaign_id, "agent_name": "mood_board_director"},
            )
            gcs_urls.append(gcs_uri)

        tool_context.state["mood_board_urls"] = gcs_urls

        logger.info(
            "Generated %d mood board images for campaign %s",
            len(gcs_urls), real_campaign_id,
        )
        return {"image_count": len(gcs_urls), "gcs_urls": gcs_urls}

    except Exception as exc:
        logger.error(
            "Failed to generate mood board images for campaign %s: %s",
            real_campaign_id, exc,
        )
        return {"error": str(exc)}


# ── Tool 2: Assemble Mood Board PDF ────────────────────────────────────


async def assemble_mood_board_pdf(
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Assemble a branded PDF mood board from generated images.

    Downloads images from GCS, uses reportlab to create a branded PDF
    with the brand name, color swatches, typography specs, and images
    in a grid layout. Uploads the final PDF to GCS.

    Args:
        campaign_id: The campaign this mood board belongs to.
        tool_context: ADK tool context for state access.

    Returns:
        The GCS URI of the mood board PDF.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        brand_dna_dict = tool_context.state.get("brand_dna")
        mood_board_urls = tool_context.state.get("mood_board_urls", [])

        if not brand_dna_dict:
            raise ValueError("No brand_dna in session state.")
        if not mood_board_urls:
            raise ValueError("No mood_board_urls in session state. Call generate_mood_board_images first.")

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Download all images
        images_data: list[bytes] = []
        for url in mood_board_urls:
            blob_path = _gcs_path_from_url(url)
            img_bytes = await asyncio.to_thread(download_blob, blob_path)
            images_data.append(img_bytes)

        # Create PDF
        buffer = io.BytesIO()
        width, height = A4
        c = canvas.Canvas(buffer, pagesize=A4)

        # Title
        c.setFont("Helvetica-Bold", 24)
        c.drawString(50, height - 50, f"{brand_dna.brand_name} — Mood Board")

        # Color swatches
        c.setFont("Helvetica", 10)
        palette = brand_dna.color_palette
        swatch_colors = [
            ("Primary", palette.primary),
            ("Secondary", palette.secondary),
            ("Accent", palette.accent),
            ("Background", palette.background),
            ("Text", palette.text),
        ]
        x_start = 50
        for j, (label, hex_color) in enumerate(swatch_colors):
            x = x_start + j * 100
            r = int(hex_color[1:3], 16) / 255
            g = int(hex_color[3:5], 16) / 255
            b = int(hex_color[5:7], 16) / 255
            c.setFillColor(rl_colors.Color(r, g, b))
            c.rect(x, height - 90, 30, 30, fill=1)
            c.setFillColor(rl_colors.black)
            c.drawString(x, height - 105, f"{label}: {hex_color}")

        # Typography
        c.setFont("Helvetica", 11)
        c.drawString(50, height - 130, f"Heading: {brand_dna.typography.heading_font}")
        c.drawString(50, height - 145, f"Body: {brand_dna.typography.body_font}")
        c.drawString(50, height - 160, f"Feel: {brand_dna.typography.font_personality}")

        # Images in 2x3 grid
        img_width = 240
        img_height = 180
        margin = 20
        y_start = height - 190

        for idx, img_bytes in enumerate(images_data[:6]):
            row = idx // 2
            col = idx % 2
            x = 50 + col * (img_width + margin)
            y = y_start - (row + 1) * (img_height + margin)

            img_reader = ImageReader(io.BytesIO(img_bytes))
            c.drawImage(img_reader, x, y, width=img_width, height=img_height, preserveAspectRatio=True)

        c.save()
        pdf_bytes = buffer.getvalue()

        # Upload PDF
        gcs_path = f"campaigns/{real_campaign_id}/production/mood_board/mood_board.pdf"
        gcs_uri = await asyncio.to_thread(
            upload_blob,
            source_data=pdf_bytes,
            destination_path=gcs_path,
            content_type="application/pdf",
            metadata={"campaign_id": real_campaign_id, "agent_name": "mood_board_director"},
        )

        logger.info("Mood board PDF assembled at %s for campaign %s", gcs_uri, real_campaign_id)
        return gcs_uri

    except Exception as exc:
        logger.error(
            "Failed to assemble mood board PDF for campaign %s: %s",
            real_campaign_id, exc,
        )
        raise
