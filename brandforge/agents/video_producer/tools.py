"""FunctionTool implementations for the Video Producer Agent.

Generates videos using Veo 3.1, adds voiceover via Cloud TTS,
and composes final MP4 with FFmpeg.
"""

import asyncio
import logging
import subprocess
import tempfile
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.video_producer.prompts import VEO_PROMPT_TEMPLATE
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import GENERATED_VIDEOS_COLLECTION, save_document
from brandforge.shared.models import (
    AgentRun,
    AgentStatus,
    BrandDNA,
    GeneratedVideo,
    VideoScript,
    VoiceConfig,
)
from brandforge.shared.retry import retry_with_backoff
from brandforge.shared.storage import download_blob, upload_blob

logger = logging.getLogger(__name__)

VEO_MODEL = "veo-3.1-generate-001"

# ── Gemini/Veo client singleton ────────────────────────────────────────

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


# ── Tool 1: Submit Veo Generation ──────────────────────────────────────


async def submit_veo_generation(
    campaign_id: str,
    script_id: str,
    tool_context: ToolContext,
) -> dict:
    """Submit a Veo 3.1 video generation job from a video script.

    Reads the matching script from video_scripts_data in session state.
    Builds a Veo prompt from the scenes' visual descriptions and emotions.

    Args:
        campaign_id: The campaign this video belongs to.
        script_id: The specific script to generate video for.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with operation_name and status.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        scripts_data = tool_context.state.get("video_scripts_data")
        if not scripts_data:
            return {"error": "No video_scripts_data in session state. Scriptwriter must run first.", "status": "failed"}

        brand_dna_dict = tool_context.state.get("brand_dna")
        if not brand_dna_dict:
            return {"error": "No brand_dna in session state.", "status": "failed"}

        # Find the matching script
        script_dict = None
        for s in scripts_data:
            if s.get("id") == script_id:
                script_dict = s
                break

        if not script_dict:
            # Try first script if exact ID not found
            script_dict = scripts_data[0]
            script_id = script_dict["id"]

        script = VideoScript.model_validate(script_dict)
        brand_dna = BrandDNA.model_validate(brand_dna_dict)

        # Build scene descriptions
        scene_descs = "\n".join(
            f"Scene {s.scene_number} ({s.duration_seconds}s): {s.visual_description} — Emotion: {s.emotion}"
            for s in script.scenes
        )
        emotion_arc = " → ".join(s.emotion for s in script.scenes)

        prompt = VEO_PROMPT_TEMPLATE.format(
            duration_seconds=script.duration_seconds,
            scene_descriptions=scene_descs,
            visual_direction=brand_dna.visual_direction,
            primary_color=brand_dna.color_palette.primary,
            secondary_color=brand_dna.color_palette.secondary,
            accent_color=brand_dna.color_palette.accent,
            emotion_arc=emotion_arc,
            aspect_ratio=script.aspect_ratio,
        )
        # Truncate prompt
        if len(prompt) > 1900:
            prompt = prompt[:1900]

        logger.info(
            "Submitting Veo generation for script %s (campaign %s)",
            script_id, real_campaign_id,
        )

        client = _get_genai_client()

        async def _submit() -> object:
            """Submit video generation to Veo."""
            return await asyncio.to_thread(
                client.models.generate_videos,
                model=VEO_MODEL,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio=script.aspect_ratio,
                    number_of_videos=1,
                ),
            )

        operation = await retry_with_backoff(_submit)
        operation_name = getattr(operation, "name", str(operation))

        # Store operation info in state
        veo_ops = tool_context.state.get("veo_operations", {})
        veo_ops[script_id] = {
            "operation_name": operation_name,
            "status": "submitted",
            "campaign_id": real_campaign_id,
        }
        tool_context.state["veo_operations"] = veo_ops

        logger.info("Veo job submitted: %s", operation_name)
        return {"operation_name": operation_name, "status": "submitted"}

    except Exception as exc:
        logger.error(
            "Failed to submit Veo generation for script %s: %s",
            script_id, exc,
        )
        return {"error": str(exc), "status": "failed"}


# ── Tool 2: Poll Veo Operation ─────────────────────────────────────────


async def poll_veo_operation(
    operation_name: str,
    timeout_seconds: int,
    tool_context: ToolContext,
) -> dict:
    """Poll a Veo operation until complete or timeout.

    Checks every 30 seconds, up to the specified timeout (default 600s / 10 min).

    Args:
        operation_name: The Veo operation name/ID to poll.
        timeout_seconds: Maximum seconds to wait before marking as failed.
        tool_context: ADK tool context for state access.

    Returns:
        A dict with status and video_uri if complete.
    """
    try:
        client = _get_genai_client()
        poll_interval = 30
        elapsed = 0

        logger.info("Polling Veo operation %s (timeout=%ds)", operation_name, timeout_seconds)

        # Construct a typed operation object from the name string
        op_ref = types.GenerateVideosOperation(name=operation_name)

        while elapsed < timeout_seconds:
            operation = await asyncio.to_thread(
                client.operations.get,
                operation=op_ref,
            )

            if hasattr(operation, "done") and operation.done:
                # Extract video data from result — Veo may return inline bytes or a URI
                video_uri = ""
                if hasattr(operation, "response") and operation.response:
                    resp = operation.response
                    if hasattr(resp, "generated_videos") and resp.generated_videos:
                        video_obj = resp.generated_videos[0]
                        if hasattr(video_obj, "video"):
                            vid = video_obj.video
                            # Check for URI first, then inline bytes
                            if hasattr(vid, "uri") and vid.uri:
                                video_uri = vid.uri
                            elif hasattr(vid, "video_bytes") and vid.video_bytes:
                                # Upload raw bytes to GCS
                                veo_ops = tool_context.state.get("veo_operations", {})
                                campaign_id = ""
                                for sid, info in veo_ops.items():
                                    if info.get("operation_name") == operation_name:
                                        campaign_id = info.get("campaign_id", "unknown")
                                        break
                                raw_path = f"campaigns/{campaign_id}/production/videos/raw/veo_{operation_name.split('/')[-1]}.mp4"
                                video_uri = await asyncio.to_thread(
                                    upload_blob,
                                    source_data=vid.video_bytes,
                                    destination_path=raw_path,
                                    content_type="video/mp4",
                                    metadata={"campaign_id": campaign_id, "agent_name": "video_producer"},
                                )
                    if not video_uri:
                        video_uri = str(resp)

                logger.info("Veo operation complete: %s", video_uri[:200])
                return {"status": "complete", "video_uri": video_uri}

            # Update op_ref for next poll cycle
            op_ref = operation

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            logger.info("Veo poll: %ds/%ds elapsed", elapsed, timeout_seconds)

        logger.warning("Veo operation timed out after %ds: %s", timeout_seconds, operation_name)
        return {"status": "failed", "error": f"Timeout after {timeout_seconds}s"}

    except Exception as exc:
        logger.error("Failed to poll Veo operation %s: %s", operation_name, exc)
        return {"status": "failed", "error": str(exc)}


# ── Tool 3: Generate Voiceover ─────────────────────────────────────────


async def generate_voiceover(
    script_id: str,
    tool_context: ToolContext,
) -> str:
    """Generate voiceover audio via Cloud TTS from script voiceover text.

    Concatenates all scene voiceover texts from the matching script and
    synthesizes speech using Google Cloud Text-to-Speech.

    Args:
        script_id: The script to generate voiceover for.
        tool_context: ADK tool context for state access.

    Returns:
        The GCS URI of the generated audio WAV file.
    """
    try:
        from google.cloud import texttospeech

        scripts_data = tool_context.state.get("video_scripts_data", [])
        brand_dna_dict = tool_context.state.get("brand_dna")

        # Find matching script
        script_dict = None
        for s in scripts_data:
            if s.get("id") == script_id:
                script_dict = s
                break
        if not script_dict and scripts_data:
            script_dict = scripts_data[0]
            script_id = script_dict["id"]

        if not script_dict:
            raise ValueError("No matching script found for voiceover generation.")

        script = VideoScript.model_validate(script_dict)

        # Concatenate voiceover texts with pauses
        voiceover_text = ". ".join(s.voiceover for s in script.scenes if s.voiceover)

        # Get voice config from state or use defaults
        voice_config = VoiceConfig()

        logger.info("Generating voiceover for script %s", script_id)

        tts_client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=voiceover_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=voice_config.language_code,
            name=voice_config.voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=voice_config.speaking_rate,
            pitch=voice_config.pitch,
        )

        response = await asyncio.to_thread(
            tts_client.synthesize_speech,
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        campaign_id = script.campaign_id
        gcs_path = f"campaigns/{campaign_id}/production/videos/audio/{script_id}.wav"
        gcs_uri = await asyncio.to_thread(
            upload_blob,
            source_data=response.audio_content,
            destination_path=gcs_path,
            content_type="audio/wav",
            metadata={"campaign_id": campaign_id, "agent_name": "video_producer"},
        )

        logger.info("Voiceover generated at %s for script %s", gcs_uri, script_id)
        return gcs_uri

    except Exception as exc:
        logger.error("Failed to generate voiceover for script %s: %s", script_id, exc)
        return f"Error generating voiceover: {exc}"


# ── Tool 4: Compose Final Video ────────────────────────────────────────


async def compose_final_video(
    campaign_id: str,
    script_id: str,
    video_uri: str,
    audio_uri: str,
    tool_context: ToolContext,
) -> str:
    """Compose final video by combining raw Veo video with TTS audio.

    Downloads raw video and audio from GCS, runs FFmpeg to merge them,
    and uploads the final MP4. Creates a GeneratedVideo record.

    Args:
        campaign_id: The campaign this video belongs to.
        script_id: The script this video is based on.
        video_uri: GCS URI of the raw Veo video.
        audio_uri: GCS URI of the voiceover audio.
        tool_context: ADK tool context for state access.

    Returns:
        The GCS URI of the final composed MP4.
    """
    # Always use the real campaign_id from session state.
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        scripts_data = tool_context.state.get("video_scripts_data", [])

        # Find matching script for metadata
        script_dict = None
        for s in scripts_data:
            if s.get("id") == script_id:
                script_dict = s
                break
        if not script_dict and scripts_data:
            script_dict = scripts_data[0]

        script = VideoScript.model_validate(script_dict) if script_dict else None

        # Download video and audio
        video_path = _gcs_path_from_url(video_uri)
        audio_path = _gcs_path_from_url(audio_uri)

        video_bytes = await asyncio.to_thread(download_blob, video_path)
        audio_bytes = await asyncio.to_thread(download_blob, audio_path)

        # Compose with FFmpeg
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            vf.write(video_bytes)
            video_tmp = vf.name

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as af:
            af.write(audio_bytes)
            audio_tmp = af.name

        output_tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_tmp,
            "-i", audio_tmp,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_tmp,
        ]

        logger.info("Running FFmpeg composition for script %s", script_id)
        process = await asyncio.to_thread(
            subprocess.run,
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if process.returncode != 0:
            logger.error("FFmpeg failed: %s", process.stderr)
            raise RuntimeError(f"FFmpeg composition failed: {process.stderr[:500]}")

        # Read and upload final video
        with open(output_tmp, "rb") as f:
            final_bytes = f.read()

        gcs_path = f"campaigns/{real_campaign_id}/production/videos/final/{script_id}.mp4"
        gcs_uri = await asyncio.to_thread(
            upload_blob,
            source_data=final_bytes,
            destination_path=gcs_path,
            content_type="video/mp4",
            metadata={"campaign_id": real_campaign_id, "agent_name": "video_producer"},
        )

        # Upload raw video too
        raw_gcs_path = f"campaigns/{real_campaign_id}/production/videos/raw/{script_id}.mp4"
        raw_gcs_uri = await asyncio.to_thread(
            upload_blob,
            source_data=video_bytes,
            destination_path=raw_gcs_path,
            content_type="video/mp4",
            metadata={"campaign_id": real_campaign_id, "agent_name": "video_producer"},
        )

        # Retrieve operation info
        veo_ops = tool_context.state.get("veo_operations", {})
        op_info = veo_ops.get(script_id, {})

        # Create GeneratedVideo record
        gen_video = GeneratedVideo(
            campaign_id=real_campaign_id,
            script_id=script_id,
            platform=script.platform if script else "instagram",
            duration_seconds=script.duration_seconds if script else 30,
            aspect_ratio=script.aspect_ratio if script else "9:16",
            gcs_url_raw=raw_gcs_uri,
            gcs_url_final=gcs_uri,
            operation_id=op_info.get("operation_name", "unknown"),
            generation_status="complete",
        )

        await save_document(
            GENERATED_VIDEOS_COLLECTION,
            gen_video.id,
            gen_video.model_dump(mode="json"),
        )

        # Store in session state
        videos_data = tool_context.state.get("generated_videos_data", [])
        videos_data.append(gen_video.model_dump(mode="json"))
        tool_context.state["generated_videos_data"] = videos_data

        logger.info("Final video composed at %s for script %s", gcs_uri, script_id)
        return gcs_uri

    except Exception as exc:
        logger.error(
            "Failed to compose final video for script %s: %s",
            script_id, exc,
        )
        return f"Error composing final video: {exc}"
