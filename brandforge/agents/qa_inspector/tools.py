"""FunctionTool implementations for the Brand QA Inspector Agent.

Reviews all generated campaign assets (images, videos, copy) against
Brand DNA using Gemini multimodal analysis. Scores, approves/rejects,
and triggers regeneration for non-compliant assets.
"""

import asyncio
import io
import json
import logging
import tempfile
from typing import Optional

import cv2
import numpy as np
from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.qa_inspector.prompts import (
    COPY_REVIEW_PROMPT_TEMPLATE,
    CORRECTION_PROMPT_TEMPLATE,
    IMAGE_REVIEW_PROMPT_TEMPLATE,
    QA_SCORING_PROMPT,
    VIDEO_REVIEW_PROMPT_TEMPLATE,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import (
    QA_RESULTS_COLLECTION,
    QA_SUMMARIES_COLLECTION,
    save_document,
)
from brandforge.shared.models import (
    BrandDNA,
    CampaignQASummary,
    CopyPackage,
    GeneratedImage,
    GeneratedVideo,
    QAResult,
    QAViolation,
)
from brandforge.shared.storage import download_blob, upload_blob

logger = logging.getLogger(__name__)

AGENT_MODEL = "gemini-2.0-flash"
QA_PASS_THRESHOLD = 0.80
MAX_REGENERATION_ATTEMPTS = 2

# ── Gemini client singleton ──────────────────────────────────────────

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


def _gcs_path_from_url(gcs_url: str) -> str:
    """Extract the object path from a gs:// URL.

    Args:
        gcs_url: A GCS URL like gs://bucket/path/to/file.

    Returns:
        The object path portion (e.g. 'path/to/file').
    """
    parts = gcs_url.replace("gs://", "").split("/", 1)
    return parts[1] if len(parts) > 1 else ""


def _parse_qa_json(text: str) -> dict:
    """Parse JSON from Gemini response text, handling markdown fences.

    Args:
        text: Raw response text possibly wrapped in ```json fences.

    Returns:
        Parsed dict from JSON.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    return json.loads(cleaned)


def _build_qa_result(
    campaign_id: str,
    asset_id: str,
    asset_type: str,
    qa_data: dict,
    attempt_number: int = 1,
) -> QAResult:
    """Build a QAResult from parsed Gemini QA output.

    Args:
        campaign_id: The campaign being reviewed.
        asset_id: ID of the asset under review.
        asset_type: One of "image", "video", "copy".
        qa_data: Parsed JSON dict from Gemini.
        attempt_number: Current attempt (1 or 2).

    Returns:
        A validated QAResult instance.
    """
    overall = float(qa_data.get("overall_score", 0.0))
    status = "approved" if overall >= QA_PASS_THRESHOLD else "failed"
    if status == "failed" and attempt_number >= MAX_REGENERATION_ATTEMPTS:
        status = "escalated"

    violations = []
    for v in qa_data.get("violations", []):
        violations.append(QAViolation(
            category=v.get("category", "unknown"),
            severity=v.get("severity", "moderate"),
            description=v.get("description", "No details provided"),
            location=v.get("location"),
            expected=v.get("expected", ""),
            found=v.get("found", ""),
        ))

    return QAResult(
        campaign_id=campaign_id,
        asset_id=asset_id,
        asset_type=asset_type,
        overall_score=max(0.0, min(1.0, overall)),
        color_compliance=max(0.0, min(1.0, float(qa_data.get("color_compliance", 0.0)))),
        tone_compliance=max(0.0, min(1.0, float(qa_data.get("tone_compliance", 0.0)))),
        visual_energy_compliance=max(0.0, min(1.0, float(qa_data.get("visual_energy_compliance", 0.0)))),
        messaging_compliance=max(0.0, min(1.0, float(qa_data.get("messaging_compliance", 0.0)))),
        status=status,
        violations=violations,
        approver_notes=qa_data.get("approver_notes", ""),
        attempt_number=attempt_number,
    )


# ── Tool: Review Image Asset ──────────────────────────────────────────


async def review_image_asset(
    campaign_id: str,
    asset_id: str,
    tool_context: ToolContext,
) -> dict:
    """Review a generated image against Brand DNA using Gemini Vision.

    Downloads the image from GCS and sends it to Gemini multimodal
    for brand compliance scoring.

    Args:
        campaign_id: The campaign ID.
        asset_id: The GeneratedImage ID to review.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with QA scores and violation details.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            return {"error": "No brand_dna found in session state."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Find the image in session state
        images_data = tool_context.state.get("generated_images_data", [])
        image_data = None
        for img in images_data:
            if img.get("id") == asset_id:
                image_data = img
                break

        if not image_data:
            return {"error": f"Image asset {asset_id} not found in session state."}

        image = GeneratedImage.model_validate(image_data)

        # Download image bytes from GCS
        gcs_path = _gcs_path_from_url(image.gcs_url)
        image_bytes = await asyncio.to_thread(download_blob, gcs_path)

        # Build review prompt
        prompt_text = IMAGE_REVIEW_PROMPT_TEMPLATE.format(
            brand_name=brand_dna.brand_name,
            primary=brand_dna.color_palette.primary,
            secondary=brand_dna.color_palette.secondary,
            accent=brand_dna.color_palette.accent,
            background=brand_dna.color_palette.background,
            text_color=brand_dna.color_palette.text,
            visual_direction=brand_dna.visual_direction,
            brand_personality=", ".join(brand_dna.brand_personality),
            tone_of_voice=brand_dna.tone_of_voice,
            platform=image.platform.value,
            use_case=image.spec.use_case,
            asset_id=asset_id,
            scoring_rubric=QA_SCORING_PROMPT,
        )

        # Send to Gemini Vision (multimodal)
        client = _get_genai_client()

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=[image_part, prompt_text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        qa_data = _parse_qa_json(response.text)
        attempt = tool_context.state.get("qa_attempts", {}).get(asset_id, 1)

        qa_result = _build_qa_result(real_campaign_id, asset_id, "image", qa_data, attempt)

        # Store in session state for later aggregation
        qa_results = tool_context.state.get("qa_results", [])
        qa_results.append(qa_result.model_dump(mode="json"))
        tool_context.state["qa_results"] = qa_results

        logger.info(
            "Image QA complete: asset=%s score=%.2f status=%s",
            asset_id, qa_result.overall_score, qa_result.status,
        )
        return {
            "asset_id": asset_id,
            "overall_score": qa_result.overall_score,
            "status": qa_result.status,
            "violations_count": len(qa_result.violations),
            "approver_notes": qa_result.approver_notes,
        }

    except Exception as exc:
        logger.error("Failed to review image asset %s: %s", asset_id, exc)
        return {"error": str(exc)}


# ── Tool: Extract Video Frames ────────────────────────────────────────


async def _extract_video_frames(
    video_bytes: bytes,
    campaign_id: str,
    video_id: str,
    num_frames: int = 5,
) -> list[bytes]:
    """Extract keyframes from video bytes using OpenCV.

    Samples frames at 0%, 25%, 50%, 75%, 100% of duration.

    Args:
        video_bytes: Raw video file bytes.
        campaign_id: Campaign ID for GCS path.
        video_id: Video asset ID for GCS path.
        num_frames: Number of frames to extract (default 5).

    Returns:
        List of JPEG-encoded frame byte arrays.
    """
    def _extract(data: bytes) -> list[bytes]:
        """Synchronous frame extraction via OpenCV."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                raise ValueError("Video has no frames")

            frame_indices = [
                int(total_frames * pct) for pct in
                [i / (num_frames - 1) for i in range(num_frames)]
            ]
            # Clamp last index
            frame_indices[-1] = min(frame_indices[-1], total_frames - 1)

            frames: list[bytes] = []
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    _, buf = cv2.imencode(".jpg", frame)
                    frames.append(buf.tobytes())
                else:
                    logger.warning("Failed to read frame %d from video %s", idx, video_id)

            return frames
        finally:
            cap.release()

    return await asyncio.to_thread(_extract, video_bytes)


# ── Tool: Review Video Asset ──────────────────────────────────────────


async def review_video_asset(
    campaign_id: str,
    asset_id: str,
    tool_context: ToolContext,
) -> dict:
    """Review a generated video against Brand DNA using Gemini Vision.

    Extracts 5 keyframes via OpenCV and sends them to Gemini for
    multimodal brand compliance analysis.

    Args:
        campaign_id: The campaign ID.
        asset_id: The GeneratedVideo ID to review.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with QA scores and violation details.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            return {"error": "No brand_dna found in session state."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Find the video in session state
        videos_data = tool_context.state.get("generated_videos_data", [])
        video_data = None
        for vid in videos_data:
            if vid.get("id") == asset_id:
                video_data = vid
                break

        if not video_data:
            return {"error": f"Video asset {asset_id} not found in session state."}

        video = GeneratedVideo.model_validate(video_data)

        # Download video and extract frames
        gcs_path = _gcs_path_from_url(video.gcs_url_final)
        video_bytes = await asyncio.to_thread(download_blob, gcs_path)

        frames = await _extract_video_frames(
            video_bytes, real_campaign_id, asset_id, num_frames=5
        )

        if not frames:
            return {"error": f"No frames extracted from video {asset_id}."}

        # Upload frames to GCS for audit trail
        frame_urls = []
        for i, frame_bytes in enumerate(frames):
            frame_path = f"campaigns/{real_campaign_id}/qa/frames/{asset_id}/frame_{i}.jpg"
            frame_url = await asyncio.to_thread(
                upload_blob,
                source_data=frame_bytes,
                destination_path=frame_path,
                content_type="image/jpeg",
                metadata={"campaign_id": real_campaign_id, "agent_name": "qa_inspector"},
            )
            frame_urls.append(frame_url)

        # Build multimodal content: all frames + review prompt
        prompt_text = VIDEO_REVIEW_PROMPT_TEMPLATE.format(
            brand_name=brand_dna.brand_name,
            primary=brand_dna.color_palette.primary,
            secondary=brand_dna.color_palette.secondary,
            accent=brand_dna.color_palette.accent,
            background=brand_dna.color_palette.background,
            text_color=brand_dna.color_palette.text,
            visual_direction=brand_dna.visual_direction,
            brand_personality=", ".join(brand_dna.brand_personality),
            tone_of_voice=brand_dna.tone_of_voice,
            platform=video.platform.value,
            duration=video.duration_seconds,
            asset_id=asset_id,
            num_frames=len(frames),
            scoring_rubric=QA_SCORING_PROMPT,
        )

        # Build multimodal parts: frames as images + text prompt
        parts: list[types.Part] = []
        for i, frame_bytes in enumerate(frames):
            parts.append(types.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=prompt_text))

        client = _get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        qa_data = _parse_qa_json(response.text)
        attempt = tool_context.state.get("qa_attempts", {}).get(asset_id, 1)

        qa_result = _build_qa_result(real_campaign_id, asset_id, "video", qa_data, attempt)

        # Store in session state
        qa_results = tool_context.state.get("qa_results", [])
        qa_results.append(qa_result.model_dump(mode="json"))
        tool_context.state["qa_results"] = qa_results

        logger.info(
            "Video QA complete: asset=%s score=%.2f status=%s frames=%d",
            asset_id, qa_result.overall_score, qa_result.status, len(frames),
        )
        return {
            "asset_id": asset_id,
            "overall_score": qa_result.overall_score,
            "status": qa_result.status,
            "violations_count": len(qa_result.violations),
            "frames_analyzed": len(frames),
            "frame_urls": frame_urls,
        }

    except Exception as exc:
        logger.error("Failed to review video asset %s: %s", asset_id, exc)
        return {"error": str(exc)}


# ── Tool: Review Copy Asset ───────────────────────────────────────────


async def review_copy_asset(
    campaign_id: str,
    platform: str,
    tool_context: ToolContext,
) -> dict:
    """Review campaign copy for a platform against Brand DNA.

    Uses Gemini text analysis to check tone, forbidden words,
    and messaging pillar alignment.

    Args:
        campaign_id: The campaign ID.
        platform: The platform name (e.g. "instagram").
        tool_context: ADK tool context for state access.

    Returns:
        A dict with QA scores and violation details.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            return {"error": "No brand_dna found in session state."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Find copy package in session state
        copy_data = tool_context.state.get("copy_package_data")
        if not copy_data:
            return {"error": "No copy_package_data found in session state."}

        copy_pkg = CopyPackage.model_validate(copy_data)

        # Find the platform copy
        platform_copy = None
        for pc in copy_pkg.platform_copies:
            if pc.platform.value == platform:
                platform_copy = pc
                break

        if not platform_copy:
            return {"error": f"No copy found for platform '{platform}'."}

        # Build messaging pillars text
        pillars_text = "\n".join(
            f"- {p.title}: {p.one_liner}" for p in brand_dna.messaging_pillars
        )

        prompt_text = COPY_REVIEW_PROMPT_TEMPLATE.format(
            brand_name=brand_dna.brand_name,
            tone_of_voice=brand_dna.tone_of_voice,
            brand_personality=", ".join(brand_dna.brand_personality),
            messaging_pillars=pillars_text,
            do_not_use=", ".join(brand_dna.do_not_use),
            platform=platform,
            caption=platform_copy.caption,
            headline=platform_copy.headline,
            cta_text=platform_copy.cta_text,
            hashtags=", ".join(platform_copy.hashtags),
            scoring_rubric=QA_SCORING_PROMPT,
        )

        client = _get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        qa_data = _parse_qa_json(response.text)
        asset_id = f"copy_{platform}_{copy_pkg.id}"
        attempt = tool_context.state.get("qa_attempts", {}).get(asset_id, 1)

        qa_result = _build_qa_result(real_campaign_id, asset_id, "copy", qa_data, attempt)

        # Store in session state
        qa_results = tool_context.state.get("qa_results", [])
        qa_results.append(qa_result.model_dump(mode="json"))
        tool_context.state["qa_results"] = qa_results

        logger.info(
            "Copy QA complete: platform=%s score=%.2f status=%s",
            platform, qa_result.overall_score, qa_result.status,
        )
        return {
            "asset_id": asset_id,
            "platform": platform,
            "overall_score": qa_result.overall_score,
            "status": qa_result.status,
            "violations_count": len(qa_result.violations),
        }

    except Exception as exc:
        logger.error("Failed to review copy for platform %s: %s", platform, exc)
        return {"error": str(exc)}


# ── Tool: Store QA Result ─────────────────────────────────────────────


async def store_qa_result(
    campaign_id: str,
    asset_id: str,
    tool_context: ToolContext,
) -> dict:
    """Persist a QA result to Firestore.

    Reads the latest QA result for the given asset from session state
    and saves it to the qa_results Firestore collection.

    Args:
        campaign_id: The campaign ID.
        asset_id: The asset ID whose QA result to persist.
        tool_context: ADK tool context for state access.

    Returns:
        A dict confirming the stored result ID.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        qa_results = tool_context.state.get("qa_results", [])

        # Find the result for this asset (most recent)
        target_result = None
        for r in reversed(qa_results):
            if r.get("asset_id") == asset_id:
                target_result = r
                break

        if not target_result:
            return {"error": f"No QA result found for asset {asset_id}."}

        qa_result = QAResult.model_validate(target_result)

        await save_document(
            QA_RESULTS_COLLECTION,
            qa_result.id,
            qa_result.model_dump(mode="json"),
        )

        logger.info("Stored QA result %s for asset %s", qa_result.id, asset_id)
        return {"qa_result_id": qa_result.id, "status": qa_result.status}

    except Exception as exc:
        logger.error("Failed to store QA result for asset %s: %s", asset_id, exc)
        return {"error": str(exc)}


# ── Tool: Generate Correction Prompt ──────────────────────────────────


async def generate_correction_prompt(
    campaign_id: str,
    asset_id: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a specific correction prompt for a failed asset.

    Creates a targeted regeneration prompt based on the QA violations
    and stores it in session state for the production agent.

    Args:
        campaign_id: The campaign ID.
        asset_id: The failed asset ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with the correction prompt.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            return {"error": "No brand_dna found in session state."}

        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        qa_results = tool_context.state.get("qa_results", [])
        target_result = None
        for r in reversed(qa_results):
            if r.get("asset_id") == asset_id:
                target_result = r
                break

        if not target_result:
            return {"error": f"No QA result found for asset {asset_id}."}

        qa_result = QAResult.model_validate(target_result)

        # Build violations text
        violations_text = "\n".join(
            f"- [{v.severity.upper()}] {v.category}: {v.description} "
            f"(expected: {v.expected}, found: {v.found})"
            for v in qa_result.violations
        )

        palette = (
            f"primary={brand_dna.color_palette.primary}, "
            f"secondary={brand_dna.color_palette.secondary}, "
            f"accent={brand_dna.color_palette.accent}"
        )

        prompt_input = CORRECTION_PROMPT_TEMPLATE.format(
            asset_type=qa_result.asset_type,
            platform=asset_id.split("_")[1] if "_" in asset_id else "unknown",
            asset_id=asset_id,
            violations_text=violations_text or "No specific violations recorded.",
            palette=palette,
            visual_direction=brand_dna.visual_direction,
            tone_of_voice=brand_dna.tone_of_voice,
            do_not_use=", ".join(brand_dna.do_not_use),
        )

        # Use Gemini to refine the correction prompt
        client = _get_genai_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=prompt_input,
        )

        correction_prompt = response.text.strip()

        # Store correction in session state
        tool_context.state["qa_correction_prompt"] = correction_prompt

        # Also update the QA result with the correction prompt
        target_result["correction_prompt"] = correction_prompt

        logger.info("Generated correction prompt for asset %s", asset_id)
        return {
            "asset_id": asset_id,
            "correction_prompt": correction_prompt[:500],
        }

    except Exception as exc:
        logger.error(
            "Failed to generate correction prompt for %s: %s", asset_id, exc
        )
        return {"error": str(exc)}


# ── Tool: Compute Brand Coherence Score ───────────────────────────────


async def compute_brand_coherence_score(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Compute the campaign-wide Brand Coherence Score.

    Averages all asset QA scores and creates a CampaignQASummary.
    Stores the summary in Firestore and session state.

    Args:
        campaign_id: The campaign ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with the brand coherence score and asset counts.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        qa_results_data = tool_context.state.get("qa_results", [])
        if not qa_results_data:
            return {"error": "No QA results found in session state."}

        qa_results = [QAResult.model_validate(r) for r in qa_results_data]

        # Compute averages
        total_score = sum(r.overall_score for r in qa_results)
        brand_coherence_score = total_score / len(qa_results) if qa_results else 0.0

        approved = sum(1 for r in qa_results if r.status == "approved")
        failed = sum(1 for r in qa_results if r.status == "failed")
        escalated = sum(1 for r in qa_results if r.status == "escalated")

        summary = CampaignQASummary(
            campaign_id=real_campaign_id,
            brand_coherence_score=round(brand_coherence_score, 3),
            total_assets=len(qa_results),
            approved_count=approved,
            failed_count=failed,
            escalated_count=escalated,
            qa_results=qa_results,
        )

        # Save to Firestore
        await save_document(
            QA_SUMMARIES_COLLECTION,
            real_campaign_id,
            summary.model_dump(mode="json"),
        )

        # Store in session state
        tool_context.state["qa_summary"] = summary.model_dump(mode="json")
        tool_context.state["brand_coherence_score"] = summary.brand_coherence_score

        logger.info(
            "Brand coherence score for campaign %s: %.3f (%d/%d approved)",
            real_campaign_id, summary.brand_coherence_score, approved, len(qa_results),
        )
        return {
            "brand_coherence_score": summary.brand_coherence_score,
            "total_assets": summary.total_assets,
            "approved": approved,
            "failed": failed,
            "escalated": escalated,
        }

    except Exception as exc:
        logger.error(
            "Failed to compute brand coherence score for %s: %s", real_campaign_id, exc
        )
        return {"error": str(exc)}


# ── Tool: Trigger Regeneration ────────────────────────────────────────


async def trigger_regeneration(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Flag failed assets for regeneration in session state.

    For each failed (not escalated) asset, increments the attempt
    counter and sets the qa_failed state with correction details.
    Max 2 attempts per asset.

    Args:
        campaign_id: The campaign ID.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with counts of assets flagged for regeneration vs escalated.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        qa_results_data = tool_context.state.get("qa_results", [])
        qa_attempts = tool_context.state.get("qa_attempts", {})

        regeneration_needed = []
        newly_escalated = []

        for r in qa_results_data:
            if r.get("status") == "failed":
                asset_id = r["asset_id"]
                current_attempt = qa_attempts.get(asset_id, 1)

                if current_attempt >= MAX_REGENERATION_ATTEMPTS:
                    # Escalate — max attempts reached
                    r["status"] = "escalated"
                    newly_escalated.append(asset_id)
                    logger.info(
                        "Asset %s escalated after %d attempts",
                        asset_id, current_attempt,
                    )
                else:
                    # Flag for regeneration
                    qa_attempts[asset_id] = current_attempt + 1
                    regeneration_needed.append({
                        "asset_id": asset_id,
                        "asset_type": r.get("asset_type"),
                        "correction_prompt": r.get("correction_prompt", ""),
                        "attempt": current_attempt + 1,
                    })
                    logger.info(
                        "Asset %s flagged for regeneration (attempt %d)",
                        asset_id, current_attempt + 1,
                    )

        # Update session state
        tool_context.state["qa_attempts"] = qa_attempts
        tool_context.state["qa_results"] = qa_results_data

        if regeneration_needed:
            tool_context.state["qa_failed"] = regeneration_needed

        logger.info(
            "Regeneration trigger: %d to regenerate, %d escalated",
            len(regeneration_needed), len(newly_escalated),
        )
        return {
            "regeneration_count": len(regeneration_needed),
            "escalated_count": len(newly_escalated),
            "regeneration_assets": [r["asset_id"] for r in regeneration_needed],
            "escalated_assets": newly_escalated,
        }

    except Exception as exc:
        logger.error(
            "Failed to trigger regeneration for campaign %s: %s", real_campaign_id, exc
        )
        return {"error": str(exc)}
