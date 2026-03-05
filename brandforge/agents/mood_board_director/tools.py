"""Mood Board Director tool implementations — Phase 2.

Generates reference images via Gemini image preview and assembles
them into a PDF mood board for brand visual language establishment.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_BRAND_DNA,
    FIRESTORE_COLLECTION_MOOD_BOARDS,
    IMAGE_PREVIEW_MODEL,
    MAX_RETRIES,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    RETRY_BASE_DELAY_SECONDS,
    EVENT_MOODBOARD_COMPLETE,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    MoodBoardImage,
)
from brandforge.shared.utils import retry_with_backoff

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Image category definitions
# ---------------------------------------------------------------------------

_IMAGE_CATEGORIES = [
    {"category": "lifestyle", "label": "Hero lifestyle shot 1"},
    {"category": "lifestyle", "label": "Hero lifestyle shot 2"},
    {"category": "texture", "label": "Texture/material detail 1"},
    {"category": "texture", "label": "Texture/material detail 2"},
    {"category": "typography", "label": "Typography mockup"},
    {"category": "color_palette", "label": "Color palette visualization"},
]


# ---------------------------------------------------------------------------
# Tool: generate_mood_board_images
# ---------------------------------------------------------------------------


async def generate_mood_board_images(
    campaign_id: str,
    brand_dna_id: str,
    num_images: int = 6,
) -> dict[str, Any]:
    """Generate mood board reference images via Gemini image preview.

    Creates category-specific image prompts grounded in BrandDNA, generates
    images using gemini-3-pro-image-preview, and uploads them to GCS.

    Args:
        campaign_id: The campaign ID.
        brand_dna_id: The BrandDNA document ID in Firestore.
        num_images: Number of images to generate (default 6).

    Returns:
        dict with status and list of GCS URLs.
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

        config = get_config()
        results: list[dict[str, Any]] = []
        errors: list[str] = []

        categories_to_generate = _IMAGE_CATEGORIES[:num_images]

        for idx, cat_info in enumerate(categories_to_generate):
            category = cat_info["category"]
            label = cat_info["label"]

            try:
                prompt = _build_image_prompt(brand_dna_data, category, label)

                async def _generate_image(p: str = prompt) -> bytes:
                    from google import genai
                    from google.genai import types
                    import asyncio

                    client = genai.Client(
                        vertexai=True,
                        project=config.gcp_project_id,
                        location=config.gcp_region,
                    )
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=IMAGE_PREVIEW_MODEL,
                        contents=[p],
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE", "TEXT"],
                        ),
                    )
                    # Extract image bytes from response
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            return base64.b64decode(part.inline_data.data) if isinstance(
                                part.inline_data.data, str
                            ) else part.inline_data.data
                    raise ValueError("No image data in response")

                image_bytes = await retry_with_backoff(
                    _generate_image,
                    max_retries=MAX_RETRIES,
                    base_delay=RETRY_BASE_DELAY_SECONDS,
                    operation_name=f"mood_board_{category}_{idx}",
                )

                # Upload to GCS
                gcs_path = f"campaigns/{campaign_id}/mood_board/{category}_{idx}.png"
                gcs_url = await upload_blob(
                    destination_path=gcs_path,
                    data=image_bytes,
                    content_type="image/png",
                )

                mood_board_image = MoodBoardImage(
                    campaign_id=campaign_id,
                    category=category,
                    gcs_url=gcs_url,
                    generation_prompt=prompt,
                )

                # Store in Firestore
                await fs.create_document(
                    collection=FIRESTORE_COLLECTION_MOOD_BOARDS,
                    doc_id=mood_board_image.id,
                    data=mood_board_image.model_dump(mode="json"),
                )

                results.append({
                    "gcs_url": gcs_url,
                    "category": category,
                    "label": label,
                })

            except Exception as exc:
                msg = f"{label}: {exc}"
                logger.error("Mood board image failed: %s", msg)
                errors.append(msg)

        if not results:
            return {"status": "error", "error": f"All image generations failed: {errors}"}

        result: dict[str, Any] = {
            "status": "success",
            "data": results,
            "image_count": len(results),
        }
        if errors:
            result["partial_errors"] = errors

        logger.info(
            "Generated %d mood board images for campaign %s", len(results), campaign_id
        )
        return result

    except Exception as exc:
        logger.error("generate_mood_board_images failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: assemble_mood_board_pdf
# ---------------------------------------------------------------------------


async def assemble_mood_board_pdf(
    image_urls_json: str,
    brand_dna_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Assemble mood board images into a branded PDF.

    Downloads images from GCS, creates a PDF with title page, image grid,
    and brand specs page, then uploads the PDF to GCS.

    Args:
        image_urls_json: JSON array of image URL dicts with gcs_url and category.
        brand_dna_id: The BrandDNA document ID.
        campaign_id: The campaign ID.

    Returns:
        dict with status and PDF GCS URL.
    """
    try:
        import tempfile
        from pathlib import Path

        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message
        from brandforge.shared.storage import download_blob, upload_blob
        from brandforge.shared.utils import gcs_uri_to_blob_path

        # Fetch BrandDNA for brand specs page
        brand_dna_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            doc_id=brand_dna_id,
        )
        if not brand_dna_data:
            return {"status": "error", "error": f"BrandDNA {brand_dna_id} not found."}

        image_urls = json.loads(image_urls_json) if isinstance(image_urls_json, str) else image_urls_json

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Download all images
            local_images: list[tuple[str, str]] = []  # (local_path, category)
            for img_info in image_urls:
                gcs_url = img_info.get("gcs_url", "")
                category = img_info.get("category", "unknown")
                try:
                    blob_path = gcs_uri_to_blob_path(gcs_url)
                    img_bytes = await download_blob(blob_path)
                    local_path = tmp / f"{category}_{len(local_images)}.png"
                    local_path.write_bytes(img_bytes)
                    local_images.append((str(local_path), category))
                except Exception as exc:
                    logger.warning("Failed to download %s: %s", gcs_url, exc)

            # Generate PDF with ReportLab
            pdf_path = tmp / "mood_board.pdf"
            _create_mood_board_pdf(
                pdf_path=str(pdf_path),
                local_images=local_images,
                brand_dna_data=brand_dna_data,
                campaign_id=campaign_id,
            )

            # Upload PDF to GCS
            pdf_bytes = pdf_path.read_bytes()
            gcs_path = f"campaigns/{campaign_id}/mood_board/mood_board.pdf"
            pdf_gcs_url = await upload_blob(
                destination_path=gcs_path,
                data=pdf_bytes,
                content_type="application/pdf",
            )

        # AgentRun record
        agent_run = AgentRun(
            campaign_id=campaign_id,
            agent_name="mood_board_director",
            status=AgentStatus.COMPLETE,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            output_ref=gcs_path,
        )
        await fs.create_document(
            collection="agent_runs",
            doc_id=agent_run.id,
            data=agent_run.model_dump(mode="json"),
        )

        # Publish completion event
        await publish_message(
            topic=PUBSUB_TOPIC_AGENT_COMPLETE,
            message=AgentMessage(
                source_agent="mood_board_director",
                target_agent="orchestrator",
                campaign_id=campaign_id,
                event_type=EVENT_MOODBOARD_COMPLETE,
                payload={
                    "pdf_gcs_url": pdf_gcs_url,
                    "image_count": len(local_images),
                },
            ),
        )

        logger.info("Assembled mood board PDF for campaign %s", campaign_id)
        return {
            "status": "success",
            "pdf_gcs_url": pdf_gcs_url,
            "image_count": len(local_images),
        }

    except Exception as exc:
        logger.error("assemble_mood_board_pdf failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_image_prompt(
    brand_dna_data: dict[str, Any],
    category: str,
    label: str,
) -> str:
    """Build a category-specific image generation prompt grounded in BrandDNA."""
    brand_name = brand_dna_data.get("brand_name", "")
    personality = ", ".join(brand_dna_data.get("brand_personality", []))
    visual_dir = brand_dna_data.get("visual_direction", "")
    palette = brand_dna_data.get("color_palette", {})
    typography = brand_dna_data.get("typography", {})

    color_str = (
        f"primary {palette.get('primary','')}, secondary {palette.get('secondary','')}, "
        f"accent {palette.get('accent','')}, background {palette.get('background','')}"
    )

    base = (
        f"Generate a high-quality reference image for a brand mood board.\n"
        f"Brand: {brand_name}\n"
        f"Personality: {personality}\n"
        f"Visual Direction: {visual_dir}\n"
        f"Color Palette: {color_str}\n"
    )

    if category == "lifestyle":
        base += (
            f"\nCategory: {label}\n"
            f"Create a hero lifestyle photograph showing the brand in context. "
            f"Include people, environments, or usage scenarios that embody the brand "
            f"personality. Use the brand colors for environment/lighting accents."
        )
    elif category == "texture":
        base += (
            f"\nCategory: {label}\n"
            f"Create a close-up macro photograph of materials and textures that "
            f"define the brand's tactile language. Think packaging materials, "
            f"product surfaces, natural textures. Use brand color palette."
        )
    elif category == "typography":
        heading_font = typography.get("heading_font", "sans-serif")
        body_font = typography.get("body_font", "sans-serif")
        base += (
            f"\nCategory: {label}\n"
            f"Create a typography mockup layout showing '{heading_font}' as heading "
            f"and '{body_font}' as body text. Show the fonts in the brand colors, "
            f"arranged in an editorial layout on the brand background color."
        )
    elif category == "color_palette":
        base += (
            f"\nCategory: {label}\n"
            f"Create a beautiful color palette visualization with 5 color swatches: "
            f"{color_str}. Arrange as a harmonized composition with paint-chip style "
            f"or gradient design. Include hex codes as text labels."
        )

    return base


def _create_mood_board_pdf(
    pdf_path: str,
    local_images: list[tuple[str, str]],
    brand_dna_data: dict[str, Any],
    campaign_id: str,
) -> None:
    """Create a mood board PDF using ReportLab.

    Generates a PDF with:
    - Title page with brand name, campaign ID, date
    - Image grid pages with images
    - Brand specs page with colors, typography, tone
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    brand_name = brand_dna_data.get("brand_name", "Brand")
    tone = brand_dna_data.get("tone_of_voice", "")
    palette = brand_dna_data.get("color_palette", {})
    typography = brand_dna_data.get("typography", {})

    # --- Title Page ---
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(width / 2, height - 3 * inch, brand_name)
    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 3.6 * inch, "Brand Mood Board")
    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 4.2 * inch, f"Campaign: {campaign_id}")
    c.drawCentredString(
        width / 2, height - 4.6 * inch,
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
    )
    c.showPage()

    # --- Image Grid Pages ---
    if local_images:
        img_width = (width - 3 * inch) / 2
        img_height = (height - 4 * inch) / 3

        for i, (img_path, category) in enumerate(local_images):
            row = (i % 6) // 2
            col = (i % 6) % 2

            if i > 0 and i % 6 == 0:
                c.showPage()

            x = inch + col * (img_width + 0.5 * inch)
            y = height - 2 * inch - (row + 1) * (img_height + 0.3 * inch)

            try:
                c.drawImage(img_path, x, y, img_width, img_height, preserveAspectRatio=True)
                c.setFont("Helvetica", 8)
                c.drawString(x, y - 12, category.upper())
            except Exception:
                c.setFont("Helvetica", 10)
                c.drawString(x, y + img_height / 2, f"[{category} — image not available]")

        c.showPage()

    # --- Brand Specs Page ---
    c.setFont("Helvetica-Bold", 24)
    c.drawString(inch, height - 1.5 * inch, "Brand Specifications")

    y_pos = height - 2.5 * inch

    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y_pos, "Color Palette")
    y_pos -= 20
    c.setFont("Helvetica", 10)
    for name, hex_val in palette.items():
        c.drawString(inch + 20, y_pos, f"{name}: {hex_val}")
        y_pos -= 15

    y_pos -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y_pos, "Typography")
    y_pos -= 20
    c.setFont("Helvetica", 10)
    c.drawString(inch + 20, y_pos, f"Heading: {typography.get('heading_font', 'N/A')}")
    y_pos -= 15
    c.drawString(inch + 20, y_pos, f"Body: {typography.get('body_font', 'N/A')}")
    y_pos -= 15
    c.drawString(inch + 20, y_pos, f"Personality: {typography.get('font_personality', 'N/A')}")

    y_pos -= 30
    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y_pos, "Tone of Voice")
    y_pos -= 20
    c.setFont("Helvetica", 9)
    # Wrap tone text
    max_width = width - 2 * inch
    words = tone.split()
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        if c.stringWidth(test, "Helvetica", 9) < max_width:
            line = test
        else:
            c.drawString(inch + 20, y_pos, line)
            y_pos -= 12
            line = word
    if line:
        c.drawString(inch + 20, y_pos, line)

    c.save()
