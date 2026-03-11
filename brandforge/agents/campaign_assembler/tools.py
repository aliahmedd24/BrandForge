"""FunctionTool implementations for the Campaign Assembler Agent.

Packages all QA-approved campaign assets into a structured bundle:
ZIP archive, brand kit PDF, and posting schedule JSON.
"""

import asyncio
import io
import json
import logging
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from google.adk.tools import ToolContext
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from brandforge.shared.config import settings
from brandforge.shared.firestore import (
    ASSET_BUNDLES_COLLECTION,
    CAMPAIGNS_COLLECTION,
    save_document,
    update_document,
)
from brandforge.shared.models import (
    AssetBundle,
    BrandDNA,
    CampaignQASummary,
    CopyPackage,
    QAResult,
)
from brandforge.shared.storage import download_blob, upload_blob

logger = logging.getLogger(__name__)

# Platform-optimal posting times (hour in UTC)
OPTIMAL_POSTING_TIMES = {
    "instagram": [11, 14, 19],
    "linkedin": [8, 12, 17],
    "twitter_x": [9, 12, 17],
    "facebook": [9, 13, 16],
    "tiktok": [10, 14, 19],
    "youtube": [12, 15, 18],
}


def _gcs_path_from_url(gcs_url: str) -> str:
    """Extract the object path from a gs:// URL.

    Args:
        gcs_url: A GCS URL like gs://bucket/path/to/file.

    Returns:
        The object path portion.
    """
    parts = gcs_url.replace("gs://", "").split("/", 1)
    return parts[1] if len(parts) > 1 else ""


# ── Tool: Collect Approved Assets ─────────────────────────────────────


async def collect_approved_assets(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Gather all QA-approved assets from session state.

    Organizes approved images and videos by platform, and
    identifies the approved copy package.

    Args:
        campaign_id: The campaign ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with categorized approved asset inventories.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        qa_results_data = tool_context.state.get("qa_results", [])
        approved_asset_ids = {
            r["asset_id"]
            for r in qa_results_data
            if r.get("status") == "approved"
        }

        # Collect approved images by platform
        image_urls: dict[str, list[str]] = {}
        images_data = tool_context.state.get("generated_images_data", [])
        for img in images_data:
            if img.get("id") in approved_asset_ids:
                platform = img.get("platform", "unknown")
                image_urls.setdefault(platform, []).append(img.get("gcs_url", ""))

        # Collect approved videos by platform
        video_urls: dict[str, list[str]] = {}
        videos_data = tool_context.state.get("generated_videos_data", [])
        for vid in videos_data:
            if vid.get("id") in approved_asset_ids:
                platform = vid.get("platform", "unknown")
                video_urls.setdefault(platform, []).append(
                    vid.get("gcs_url_final", "")
                )

        # Copy package
        copy_data = tool_context.state.get("copy_package_data", {})
        copy_package_id = copy_data.get("id", "")

        # Store in session state for downstream tools
        tool_context.state["approved_image_urls"] = image_urls
        tool_context.state["approved_video_urls"] = video_urls
        tool_context.state["approved_copy_package_id"] = copy_package_id

        total = sum(len(v) for v in image_urls.values()) + sum(
            len(v) for v in video_urls.values()
        )

        logger.info(
            "Collected %d approved assets for campaign %s", total, real_campaign_id
        )
        return {
            "total_approved": total,
            "image_platforms": {k: len(v) for k, v in image_urls.items()},
            "video_platforms": {k: len(v) for k, v in video_urls.items()},
            "copy_package_id": copy_package_id,
        }

    except Exception as exc:
        logger.error("Failed to collect approved assets for %s: %s", real_campaign_id, exc)
        return {"error": str(exc)}


# ── Tool: Generate Brand Kit PDF ──────────────────────────────────────


async def generate_brand_kit_pdf(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a comprehensive brand kit PDF.

    Contains: cover page, brand DNA summary (palette, typography, tone),
    asset inventory, copy package, and QA summary.

    Args:
        campaign_id: The campaign ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with the GCS URL of the generated PDF.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            return {"error": "No brand_dna found in session state."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)
        qa_summary_data = tool_context.state.get("qa_summary", {})

        def _build_pdf() -> bytes:
            """Build the PDF synchronously using ReportLab."""
            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                leftMargin=0.75 * inch,
                rightMargin=0.75 * inch,
                topMargin=0.75 * inch,
                bottomMargin=0.75 * inch,
            )

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "BrandTitle",
                parent=styles["Title"],
                fontSize=28,
                spaceAfter=20,
            )
            heading_style = ParagraphStyle(
                "BrandHeading",
                parent=styles["Heading1"],
                fontSize=18,
                spaceAfter=12,
                spaceBefore=20,
            )
            body_style = styles["BodyText"]

            elements = []

            # Page 1: Cover
            elements.append(Spacer(1, 2 * inch))
            elements.append(Paragraph(f"{brand_dna.brand_name}", title_style))
            elements.append(Paragraph("Campaign Brand Kit", styles["Heading2"]))
            elements.append(Spacer(1, 0.5 * inch))
            elements.append(
                Paragraph(f"Campaign ID: {real_campaign_id}", body_style)
            )
            elements.append(
                Paragraph(f"Brand Essence: {brand_dna.brand_essence}", body_style)
            )

            coherence = qa_summary_data.get("brand_coherence_score", "N/A")
            elements.append(
                Paragraph(f"Brand Coherence Score: {coherence}", body_style)
            )
            elements.append(Spacer(1, 2 * inch))

            # Page 2: Brand DNA Summary
            elements.append(Paragraph("Brand DNA Summary", heading_style))
            elements.append(
                Paragraph(f"<b>Brand Personality:</b> {', '.join(brand_dna.brand_personality)}", body_style)
            )
            elements.append(
                Paragraph(f"<b>Tone of Voice:</b> {brand_dna.tone_of_voice}", body_style)
            )
            elements.append(
                Paragraph(f"<b>Visual Direction:</b> {brand_dna.visual_direction}", body_style)
            )
            elements.append(Spacer(1, 12))

            # Color palette table
            elements.append(Paragraph("Color Palette", styles["Heading3"]))
            palette = brand_dna.color_palette
            color_data = [
                ["Role", "Hex Code"],
                ["Primary", palette.primary],
                ["Secondary", palette.secondary],
                ["Accent", palette.accent],
                ["Background", palette.background],
                ["Text", palette.text],
            ]
            color_table = Table(color_data, colWidths=[2 * inch, 2 * inch])
            color_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
            ]))
            elements.append(color_table)
            elements.append(Spacer(1, 12))

            # Typography
            elements.append(Paragraph("Typography", styles["Heading3"]))
            elements.append(
                Paragraph(f"Heading Font: {brand_dna.typography.heading_font}", body_style)
            )
            elements.append(
                Paragraph(f"Body Font: {brand_dna.typography.body_font}", body_style)
            )
            elements.append(
                Paragraph(f"Personality: {brand_dna.typography.font_personality}", body_style)
            )

            # Page 3: Messaging Pillars
            elements.append(Paragraph("Messaging Pillars", heading_style))
            for pillar in brand_dna.messaging_pillars:
                elements.append(
                    Paragraph(f"<b>{pillar.title}:</b> {pillar.one_liner}", body_style)
                )
                for sp in pillar.supporting_points:
                    elements.append(Paragraph(f"  - {sp}", body_style))
            elements.append(Spacer(1, 12))

            # Asset Inventory
            elements.append(Paragraph("Asset Inventory", heading_style))
            image_urls = tool_context.state.get("approved_image_urls", {})
            for platform, urls in image_urls.items():
                elements.append(
                    Paragraph(f"<b>{platform}</b>: {len(urls)} images", body_style)
                )
            video_urls = tool_context.state.get("approved_video_urls", {})
            for platform, urls in video_urls.items():
                elements.append(
                    Paragraph(f"<b>{platform}</b>: {len(urls)} videos", body_style)
                )
            elements.append(Spacer(1, 12))

            # Copy Package
            copy_data = tool_context.state.get("copy_package_data", {})
            if copy_data:
                elements.append(Paragraph("Copy Package", heading_style))
                copy_pkg = CopyPackage.model_validate(copy_data)
                elements.append(
                    Paragraph(f"<b>Global Tagline:</b> {copy_pkg.global_tagline}", body_style)
                )
                for pc in copy_pkg.platform_copies:
                    elements.append(
                        Paragraph(f"<b>{pc.platform.value}:</b>", body_style)
                    )
                    elements.append(
                        Paragraph(f"  Headline: {pc.headline}", body_style)
                    )
                    elements.append(
                        Paragraph(f"  Caption: {pc.caption[:200]}...", body_style)
                    )
                    elements.append(
                        Paragraph(f"  Hashtags: {', '.join(pc.hashtags[:10])}", body_style)
                    )

            # QA Summary
            if qa_summary_data:
                elements.append(Paragraph("QA Summary", heading_style))
                elements.append(
                    Paragraph(
                        f"Brand Coherence Score: {qa_summary_data.get('brand_coherence_score', 'N/A')}",
                        body_style,
                    )
                )
                elements.append(
                    Paragraph(
                        f"Total Assets: {qa_summary_data.get('total_assets', 0)} | "
                        f"Approved: {qa_summary_data.get('approved_count', 0)} | "
                        f"Failed: {qa_summary_data.get('failed_count', 0)} | "
                        f"Escalated: {qa_summary_data.get('escalated_count', 0)}",
                        body_style,
                    )
                )

            doc.build(elements)
            return buf.getvalue()

        pdf_bytes = await asyncio.to_thread(_build_pdf)

        gcs_path = f"campaigns/{real_campaign_id}/bundle/brand_kit.pdf"
        pdf_url = await asyncio.to_thread(
            upload_blob,
            source_data=pdf_bytes,
            destination_path=gcs_path,
            content_type="application/pdf",
            metadata={"campaign_id": real_campaign_id, "agent_name": "campaign_assembler"},
        )

        tool_context.state["brand_kit_pdf_url"] = pdf_url

        logger.info("Brand kit PDF generated for campaign %s", real_campaign_id)
        return {"pdf_url": pdf_url, "size_bytes": len(pdf_bytes)}

    except Exception as exc:
        logger.error("Failed to generate brand kit PDF for %s: %s", real_campaign_id, exc)
        return {"error": str(exc)}


# ── Tool: Generate Posting Schedule ───────────────────────────────────


async def generate_posting_schedule(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a 7-day posting schedule with platform-optimal times.

    Distributes approved assets across a week with recommended
    posting times for each platform.

    Args:
        campaign_id: The campaign ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with the GCS URL of the schedule JSON.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        image_urls = tool_context.state.get("approved_image_urls", {})
        video_urls = tool_context.state.get("approved_video_urls", {})
        copy_data = tool_context.state.get("copy_package_data", {})

        start_date = datetime.now(timezone.utc) + timedelta(days=1)
        schedule: list[dict[str, Any]] = []

        # Build platform asset lists
        all_platforms = set(image_urls.keys()) | set(video_urls.keys())

        for day_offset in range(7):
            post_date = start_date + timedelta(days=day_offset)
            day_str = post_date.strftime("%Y-%m-%d")

            for platform in sorted(all_platforms):
                times = OPTIMAL_POSTING_TIMES.get(platform, [12])
                # Rotate through posting times across the week
                post_hour = times[day_offset % len(times)]

                # Select an asset for this day
                p_images = image_urls.get(platform, [])
                p_videos = video_urls.get(platform, [])
                all_assets = p_images + p_videos

                if not all_assets:
                    continue

                asset_idx = day_offset % len(all_assets)
                asset_url = all_assets[asset_idx]
                asset_type = "image" if asset_url in p_images else "video"

                schedule.append({
                    "date": day_str,
                    "time_utc": f"{post_hour:02d}:00",
                    "platform": platform,
                    "asset_type": asset_type,
                    "asset_url": asset_url,
                    "day_of_week": post_date.strftime("%A"),
                })

        schedule_json = json.dumps(
            {"campaign_id": real_campaign_id, "schedule": schedule}, indent=2
        )

        gcs_path = f"campaigns/{real_campaign_id}/bundle/posting_schedule.json"
        schedule_url = await asyncio.to_thread(
            upload_blob,
            source_data=schedule_json.encode("utf-8"),
            destination_path=gcs_path,
            content_type="application/json",
            metadata={"campaign_id": real_campaign_id, "agent_name": "campaign_assembler"},
        )

        tool_context.state["posting_schedule_url"] = schedule_url

        logger.info(
            "Posting schedule generated: %d posts over 7 days for campaign %s",
            len(schedule), real_campaign_id,
        )
        return {
            "schedule_url": schedule_url,
            "total_posts": len(schedule),
            "platforms": sorted(all_platforms),
        }

    except Exception as exc:
        logger.error(
            "Failed to generate posting schedule for %s: %s", real_campaign_id, exc
        )
        return {"error": str(exc)}


# ── Tool: Create Asset Bundle ZIP ─────────────────────────────────────


async def create_asset_bundle_zip(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Create a ZIP archive of all approved campaign assets.

    Downloads approved images, videos, and copy, then packages
    them into a single ZIP file uploaded to GCS.

    Args:
        campaign_id: The campaign ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with the GCS URL and size of the ZIP.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        image_urls = tool_context.state.get("approved_image_urls", {})
        video_urls = tool_context.state.get("approved_video_urls", {})
        copy_data = tool_context.state.get("copy_package_data", {})

        def _build_zip() -> bytes:
            """Build the ZIP archive synchronously."""
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                # Add images
                for platform, urls in image_urls.items():
                    for i, url in enumerate(urls):
                        try:
                            path = _gcs_path_from_url(url)
                            data = download_blob(path)
                            zf.writestr(
                                f"images/{platform}/image_{i + 1}.png", data
                            )
                        except Exception as e:
                            logger.warning("Skip image %s: %s", url, e)

                # Add videos
                for platform, urls in video_urls.items():
                    for i, url in enumerate(urls):
                        try:
                            path = _gcs_path_from_url(url)
                            data = download_blob(path)
                            zf.writestr(
                                f"videos/{platform}/video_{i + 1}.mp4", data
                            )
                        except Exception as e:
                            logger.warning("Skip video %s: %s", url, e)

                # Add copy package JSON
                if copy_data:
                    copy_json = json.dumps(copy_data, indent=2)
                    zf.writestr("copy/copy_package.json", copy_json)

                # Add brand kit PDF if available
                pdf_url = tool_context.state.get("brand_kit_pdf_url", "")
                if pdf_url:
                    try:
                        path = _gcs_path_from_url(pdf_url)
                        pdf_data = download_blob(path)
                        zf.writestr("brand_kit.pdf", pdf_data)
                    except Exception as e:
                        logger.warning("Skip brand kit PDF: %s", e)

                # Add posting schedule if available
                schedule_url = tool_context.state.get("posting_schedule_url", "")
                if schedule_url:
                    try:
                        path = _gcs_path_from_url(schedule_url)
                        sched_data = download_blob(path)
                        zf.writestr("posting_schedule.json", sched_data)
                    except Exception as e:
                        logger.warning("Skip posting schedule: %s", e)

            return buf.getvalue()

        zip_bytes = await asyncio.to_thread(_build_zip)

        gcs_path = f"campaigns/{real_campaign_id}/bundle/campaign_assets.zip"
        zip_url = await asyncio.to_thread(
            upload_blob,
            source_data=zip_bytes,
            destination_path=gcs_path,
            content_type="application/zip",
            metadata={"campaign_id": real_campaign_id, "agent_name": "campaign_assembler"},
        )

        tool_context.state["zip_gcs_url"] = zip_url

        logger.info(
            "Asset bundle ZIP created for campaign %s (%d bytes)",
            real_campaign_id, len(zip_bytes),
        )
        return {"zip_url": zip_url, "size_bytes": len(zip_bytes)}

    except Exception as exc:
        logger.error(
            "Failed to create asset bundle ZIP for %s: %s", real_campaign_id, exc
        )
        return {"error": str(exc)}


# ── Tool: Store Asset Bundle ──────────────────────────────────────────


async def store_asset_bundle(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Create and persist the AssetBundle record.

    Saves the bundle to Firestore and updates the Campaign document
    with the asset_bundle_id.

    Args:
        campaign_id: The campaign ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict confirming the bundle ID.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        image_urls = tool_context.state.get("approved_image_urls", {})
        video_urls = tool_context.state.get("approved_video_urls", {})
        copy_package_id = tool_context.state.get("approved_copy_package_id", "")
        zip_url = tool_context.state.get("zip_gcs_url", "")
        pdf_url = tool_context.state.get("brand_kit_pdf_url", "")
        schedule_url = tool_context.state.get("posting_schedule_url", "")
        coherence_score = tool_context.state.get("brand_coherence_score", 0.0)

        bundle = AssetBundle(
            campaign_id=real_campaign_id,
            brand_coherence_score=coherence_score,
            image_urls=image_urls,
            video_urls=video_urls,
            copy_package_id=copy_package_id,
            zip_gcs_url=zip_url,
            brand_kit_pdf_url=pdf_url,
            posting_schedule_url=schedule_url,
        )

        # Save bundle to Firestore
        await save_document(
            ASSET_BUNDLES_COLLECTION,
            bundle.id,
            bundle.model_dump(mode="json"),
        )

        # Update Campaign record with bundle ID
        await update_document(
            CAMPAIGNS_COLLECTION,
            real_campaign_id,
            {"asset_bundle_id": bundle.id, "status": "approved"},
        )

        tool_context.state["asset_bundle_id"] = bundle.id

        logger.info(
            "Asset bundle %s stored for campaign %s", bundle.id, real_campaign_id
        )
        return {
            "bundle_id": bundle.id,
            "campaign_id": real_campaign_id,
            "brand_coherence_score": coherence_score,
        }

    except Exception as exc:
        logger.error(
            "Failed to store asset bundle for %s: %s", real_campaign_id, exc
        )
        return {"error": str(exc)}
