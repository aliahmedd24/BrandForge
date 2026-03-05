"""Video Producer tool implementations — Phase 2.

Manages the full video pipeline: wait for Scriptwriter → Veo generation →
polling → Cloud TTS voiceover → FFmpeg merge → final deliverable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_BRAND_DNA,
    FIRESTORE_COLLECTION_SCRIPTS,
    MAX_RETRIES,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    RETRY_BASE_DELAY_SECONDS,
    VEO_MAX_TIMEOUT_SECONDS,
    VEO_MODEL,
    VEO_POLL_INTERVAL_SECONDS,
    EVENT_VIDEOPRODUCER_COMPLETE,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    GeneratedVideo,
    VideoScript,
    VoiceConfig,
)
from brandforge.shared.utils import retry_with_backoff

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool: wait_for_scriptwriter
# ---------------------------------------------------------------------------


async def wait_for_scriptwriter(
    campaign_id: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Poll Firestore for Scriptwriter agent completion.

    Checks every 5 seconds for a scriptwriter AgentRun with status=complete.

    Args:
        campaign_id: The campaign ID.
        timeout_seconds: Max wait time (default 5 minutes).

    Returns:
        dict with status and script IDs on success, or error on timeout.
    """
    try:
        from brandforge.shared import firestore as fs

        poll_interval = 5
        elapsed = 0

        while elapsed < timeout_seconds:
            runs = await fs.query_collection(
                collection="agent_runs",
                field="campaign_id",
                op="==",
                value=campaign_id,
            )

            for run in runs:
                if (
                    run.get("agent_name") == "scriptwriter"
                    and run.get("status") == AgentStatus.COMPLETE
                ):
                    # Fetch script IDs from the scripts collection
                    scripts = await fs.query_collection(
                        collection=FIRESTORE_COLLECTION_SCRIPTS,
                        field="campaign_id",
                        op="==",
                        value=campaign_id,
                    )
                    script_ids = [s.get("id", "") for s in scripts]
                    logger.info(
                        "Scriptwriter complete for campaign %s: %d scripts",
                        campaign_id, len(script_ids),
                    )
                    return {
                        "status": "success",
                        "script_ids": script_ids,
                        "scripts_count": len(script_ids),
                    }

            logger.info(
                "Waiting for scriptwriter (%ds/%ds)...", elapsed, timeout_seconds
            )
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return {
            "status": "error",
            "error": f"Scriptwriter did not complete within {timeout_seconds}s.",
        }

    except Exception as exc:
        logger.error("wait_for_scriptwriter failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: submit_veo_generation
# ---------------------------------------------------------------------------


async def submit_veo_generation(
    script_id: str,
    brand_dna_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Submit a Veo 3.1 video generation request.

    Fetches the VideoScript and BrandDNA, builds a Veo prompt from scene
    visual descriptions, and submits the generation request.

    Args:
        script_id: The VideoScript document ID.
        brand_dna_id: The BrandDNA document ID.
        campaign_id: The campaign ID.

    Returns:
        dict with operation_id on success.
    """
    try:
        from brandforge.shared import firestore as fs

        config = get_config()

        # Fetch script + BrandDNA
        script_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_SCRIPTS, doc_id=script_id
        )
        if not script_data:
            return {"status": "error", "error": f"Script {script_id} not found."}

        brand_dna_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA, doc_id=brand_dna_id
        )
        if not brand_dna_data:
            return {"status": "error", "error": f"BrandDNA {brand_dna_id} not found."}

        script = VideoScript(**script_data)

        # Build Veo prompt from scene descriptions
        veo_prompt = _build_veo_prompt(script, brand_dna_data)

        async def _submit() -> str:
            from google.cloud import aiplatform
            import asyncio

            # Submit to Veo via Vertex AI
            client = aiplatform.gapic.PredictionServiceClient(
                client_options={"api_endpoint": f"{config.gcp_region}-aiplatform.googleapis.com"}
            )

            endpoint = (
                f"projects/{config.gcp_project_id}/locations/{config.gcp_region}/"
                f"publishers/google/models/{VEO_MODEL}"
            )

            response = await asyncio.to_thread(
                client.predict,
                endpoint=endpoint,
                instances=[{"prompt": veo_prompt}],
                parameters={
                    "aspectRatio": script.aspect_ratio,
                    "durationSeconds": script.duration_seconds,
                },
            )

            # Extract operation ID from response
            op_id = str(uuid.uuid4())  # Placeholder — actual API returns operation
            if hasattr(response, "metadata") and response.metadata:
                op_id = str(response.metadata.get("operationId", op_id))
            return op_id

        operation_id = await retry_with_backoff(
            _submit,
            max_retries=MAX_RETRIES,
            base_delay=RETRY_BASE_DELAY_SECONDS,
            operation_name=f"veo_submit_{script_id}",
        )

        # Create GeneratedVideo record
        video = GeneratedVideo(
            campaign_id=campaign_id,
            script_id=script_id,
            platform=script.platform,
            duration_seconds=script.duration_seconds,
            aspect_ratio=script.aspect_ratio,
            gcs_url_raw="",
            operation_id=operation_id,
            generation_status="processing",
        )
        await fs.create_document(
            collection="generated_videos",
            doc_id=video.id,
            data=video.model_dump(mode="json"),
        )

        logger.info("Submitted Veo generation for script %s: op=%s", script_id, operation_id)
        return {
            "status": "success",
            "operation_id": operation_id,
            "video_id": video.id,
        }

    except Exception as exc:
        logger.error("submit_veo_generation failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: poll_veo_operation
# ---------------------------------------------------------------------------


async def poll_veo_operation(
    operation_id: str,
    timeout_seconds: int = VEO_MAX_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Poll a Veo operation until completion or timeout.

    Checks every 30 seconds. Max timeout is 10 minutes.

    Args:
        operation_id: The Veo operation ID.
        timeout_seconds: Max wait time (default from config).

    Returns:
        dict with raw video GCS URL on success, or error on timeout/failure.
    """
    try:
        config = get_config()
        elapsed = 0

        while elapsed < timeout_seconds:
            try:
                from google.cloud import aiplatform
                import asyncio

                client = aiplatform.gapic.PredictionServiceClient(
                    client_options={
                        "api_endpoint": f"{config.gcp_region}-aiplatform.googleapis.com"
                    }
                )

                # Check operation status
                op_result = await asyncio.to_thread(
                    client.get_operation,
                    name=operation_id,
                )

                if op_result.done:
                    if op_result.error.code != 0:
                        return {
                            "status": "error",
                            "error": f"Veo generation failed: {op_result.error.message}",
                        }

                    # Extract raw video URL from result
                    raw_url = ""
                    if op_result.response:
                        raw_url = str(
                            op_result.response.get("videoUri", f"gs://placeholder/{operation_id}.mp4")
                        )

                    logger.info("Veo operation %s completed", operation_id)
                    return {"status": "success", "raw_video_gcs": raw_url}

            except Exception as poll_exc:
                logger.warning("Poll attempt failed: %s", poll_exc)

            logger.info(
                "Polling Veo operation %s (%ds/%ds)...",
                operation_id, elapsed, timeout_seconds,
            )
            await asyncio.sleep(VEO_POLL_INTERVAL_SECONDS)
            elapsed += VEO_POLL_INTERVAL_SECONDS

        return {
            "status": "error",
            "error": f"Veo operation {operation_id} timed out after {timeout_seconds}s.",
        }

    except Exception as exc:
        logger.error("poll_veo_operation failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: generate_voiceover
# ---------------------------------------------------------------------------


async def generate_voiceover(
    script_id: str,
    voice_config_json: str = "",
) -> dict[str, Any]:
    """Generate TTS voiceover audio from a VideoScript.

    Concatenates all scene voiceover texts with pauses and sends to
    Google Cloud TTS with WaveNet voice.

    Args:
        script_id: The VideoScript document ID.
        voice_config_json: Optional JSON overrides for VoiceConfig.

    Returns:
        dict with audio GCS URL on success.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.storage import upload_blob

        script_data = await fs.get_document(
            collection=FIRESTORE_COLLECTION_SCRIPTS, doc_id=script_id
        )
        if not script_data:
            return {"status": "error", "error": f"Script {script_id} not found."}

        script = VideoScript(**script_data)

        # Parse voice config
        if voice_config_json:
            vc_data = json.loads(voice_config_json)
            voice_config = VoiceConfig(**vc_data)
        else:
            voice_config = VoiceConfig()

        # Build SSML from scenes
        ssml_parts = ['<speak>']
        for scene in script.scenes:
            ssml_parts.append(f"<p>{scene.voiceover}</p>")
            ssml_parts.append('<break time="500ms"/>')
        ssml_parts.append('</speak>')
        ssml = "".join(ssml_parts)

        async def _synthesize() -> bytes:
            from google.cloud import texttospeech
            import asyncio

            client = texttospeech.TextToSpeechClient()

            synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
            voice = texttospeech.VoiceSelectionParams(
                language_code=voice_config.language_code,
                name=voice_config.voice_name,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=voice_config.speaking_rate,
                pitch=voice_config.pitch,
            )

            response = await asyncio.to_thread(
                client.synthesize_speech,
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )
            return response.audio_content

        audio_bytes = await retry_with_backoff(
            _synthesize,
            max_retries=MAX_RETRIES,
            base_delay=RETRY_BASE_DELAY_SECONDS,
            operation_name=f"tts_{script_id}",
        )

        # Upload to GCS
        gcs_path = f"campaigns/{script.campaign_id}/videos/voiceover_{script_id}.mp3"
        audio_gcs_url = await upload_blob(
            destination_path=gcs_path,
            data=audio_bytes,
            content_type="audio/mpeg",
        )

        logger.info("Generated voiceover for script %s", script_id)
        return {"status": "success", "audio_gcs_url": audio_gcs_url}

    except Exception as exc:
        logger.error("generate_voiceover failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: compose_final_video
# ---------------------------------------------------------------------------


async def compose_final_video(
    raw_video_gcs: str,
    audio_gcs: str,
    campaign_id: str,
    script_id: str,
) -> dict[str, Any]:
    """Merge raw Veo video with TTS audio into final deliverable.

    Uses FFmpeg via shared/video_utils.py to compose video + audio,
    then creates a GeneratedVideo record and publishes completion.

    Args:
        raw_video_gcs: GCS URI of the raw Veo video.
        audio_gcs: GCS URI of the TTS audio file.
        campaign_id: The campaign ID.
        script_id: The VideoScript document ID.

    Returns:
        dict with final video GCS URL.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message
        from brandforge.shared.video_utils import merge_video_audio

        output_gcs_path = f"campaigns/{campaign_id}/videos/final_{script_id}.mp4"

        final_gcs_url = await merge_video_audio(
            video_gcs=raw_video_gcs,
            audio_gcs=audio_gcs,
            output_gcs_path=output_gcs_path,
        )

        # Update GeneratedVideo record if it exists
        videos = await fs.query_collection(
            collection="generated_videos",
            field="script_id",
            op="==",
            value=script_id,
        )
        if videos:
            video_doc = videos[0]
            await fs.update_document(
                collection="generated_videos",
                doc_id=video_doc["id"],
                updates={
                    "gcs_url_final": final_gcs_url,
                    "generation_status": "complete",
                },
            )

        # AgentRun record
        agent_run = AgentRun(
            campaign_id=campaign_id,
            agent_name="video_producer",
            status=AgentStatus.COMPLETE,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            output_ref=output_gcs_path,
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
                source_agent="video_producer",
                target_agent="orchestrator",
                campaign_id=campaign_id,
                event_type=EVENT_VIDEOPRODUCER_COMPLETE,
                payload={
                    "script_id": script_id,
                    "final_video_gcs": final_gcs_url,
                },
            ),
        )

        logger.info("Final video composed for script %s", script_id)
        return {"status": "success", "final_video_gcs": final_gcs_url}

    except Exception as exc:
        logger.error("compose_final_video failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_veo_prompt(
    script: VideoScript,
    brand_dna_data: dict[str, Any],
) -> str:
    """Build a Veo generation prompt from script scenes and BrandDNA."""
    visual_dir = brand_dna_data.get("visual_direction", "")
    palette = brand_dna_data.get("color_palette", {})

    parts = [
        f"Create a {script.duration_seconds}s {script.aspect_ratio} video.",
        f"Visual direction: {visual_dir}",
        f"Color palette: {palette.get('primary','')}, {palette.get('secondary','')}, {palette.get('accent','')}",
        "",
    ]

    time_marker = 0
    for scene in script.scenes:
        parts.append(
            f"[{time_marker}s-{time_marker + scene.duration_seconds}s] "
            f"{scene.visual_description} (Emotion: {scene.emotion})"
        )
        time_marker += scene.duration_seconds

    return "\n".join(parts)
