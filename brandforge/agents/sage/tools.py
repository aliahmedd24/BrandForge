"""FunctionTool implementations for the Sage Voice Orchestrator.

Provides TTS narration via Cloud TTS, voice feedback processing via
Gemini, and audio caching in GCS keyed by text hash.
"""

import asyncio
import hashlib
import json
import logging
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.sage.prompts import (
    NARRATION_TEMPLATES,
    VOICE_CLASSIFICATION_PROMPT,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.models import VoiceFeedbackResult
from brandforge.shared.storage import download_blob, upload_blob

logger = logging.getLogger(__name__)

AGENT_MODEL = "gemini-2.0-flash"
SAGE_VOICE_NAME = "en-US-Neural2-J"
SAGE_LANGUAGE_CODE = "en-US"

# ── Gemini client singleton ────────────────────────────────────────────

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


def _text_hash(text: str) -> str:
    """Generate a SHA-256 hash of text for cache keying.

    Args:
        text: The narration text to hash.

    Returns:
        A hex digest string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Tool 1: Narrate Agent Milestone ───────────────────────────────────


async def narrate_agent_milestone(
    milestone: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> str:
    """Generate narration audio for a pipeline milestone.

    Uses Cloud TTS to convert narration text to audio. Caches audio in
    GCS keyed by text hash — identical narrations return the same URL.

    Args:
        milestone: The milestone name (e.g. "campaign_start", "brand_dna_complete").
        campaign_id: The campaign this narration belongs to.

    Returns:
        GCS URL of the narration audio file.
    """
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        # Build narration text from template
        template = NARRATION_TEMPLATES.get(milestone, "")
        if not template:
            template = f"Pipeline milestone: {milestone}. Moving to next stage."

        # Fill template with context from session state
        context_vars = _extract_narration_context(milestone, tool_context)
        try:
            narration_text = template.format(**context_vars)
        except KeyError:
            narration_text = template  # Use raw template if format fails

        # Check cache
        text_hash = _text_hash(narration_text)
        cache_path = f"campaigns/{real_campaign_id}/sage/narration_{text_hash}.mp3"

        # Check if cached audio exists in GCS
        try:
            existing_bytes = await asyncio.to_thread(download_blob, cache_path)
            if existing_bytes:
                gcs_url = f"gs://{settings.gcs_bucket}/{cache_path}"
                logger.info("Narration cache hit for milestone %s", milestone)
                return gcs_url
        except Exception:
            pass  # Cache miss, generate new audio

        # Generate TTS audio
        audio_bytes = await _synthesize_speech(narration_text)

        # Upload to GCS
        gcs_url = await asyncio.to_thread(
            upload_blob,
            source_data=audio_bytes,
            destination_path=cache_path,
            content_type="audio/mpeg",
        )

        # Store narration event in session state
        narrations = tool_context.state.get("sage_narrations", [])
        narrations.append({
            "milestone": milestone,
            "text": narration_text,
            "audio_url": gcs_url,
        })
        tool_context.state["sage_narrations"] = narrations

        logger.info(
            "Sage narration generated for %s: %s (%d chars)",
            milestone, gcs_url, len(narration_text),
        )
        return gcs_url

    except Exception as exc:
        logger.error("Failed to narrate milestone %s: %s", milestone, exc)
        return ""


# ── Tool 2: Process Voice Feedback ────────────────────────────────────


async def process_voice_feedback(
    audio_gcs_url: str,
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Process user voice feedback during campaign generation.

    Transcribes audio via Gemini, classifies intent, and routes
    modifications to the appropriate sub-agent. Generates Sage's
    spoken response.

    Args:
        audio_gcs_url: GCS URL of the user's voice input.
        campaign_id: The current campaign ID.

    Returns:
        A VoiceFeedbackResult dict with transcription, intent, and response.
    """
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        # Download and transcribe audio
        blob_path = audio_gcs_url.replace(f"gs://{settings.gcs_bucket}/", "")
        audio_bytes = await asyncio.to_thread(download_blob, blob_path)

        client = _get_genai_client()

        # Transcribe
        transcribe_response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/webm"),
                "Transcribe this audio exactly. Return only the transcription text.",
            ],
        )
        transcription = transcribe_response.text.strip()

        # Classify intent
        active_agents = tool_context.state.get("active_agents", [
            "brand_strategist", "copy_editor", "image_generator",
            "video_producer", "scriptwriter",
        ])

        classify_prompt = VOICE_CLASSIFICATION_PROMPT.format(
            transcription=transcription,
            active_agents=", ".join(active_agents),
        )

        classify_response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=classify_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        classification = json.loads(classify_response.text)

        # Generate Sage's spoken response
        sage_response_text = classification.get(
            "sage_response_text",
            f"I heard you say: {transcription}. Let me process that.",
        )
        response_audio_bytes = await _synthesize_speech(sage_response_text)

        # Upload response audio
        response_hash = _text_hash(sage_response_text)
        response_path = (
            f"campaigns/{real_campaign_id}/sage/response_{response_hash}.mp3"
        )
        response_audio_url = await asyncio.to_thread(
            upload_blob,
            source_data=response_audio_bytes,
            destination_path=response_path,
            content_type="audio/mpeg",
        )

        result = VoiceFeedbackResult(
            transcription=transcription,
            intent=classification.get("intent", "question"),
            target_agent=classification.get("target_agent"),
            instruction=classification.get("instruction"),
            sage_response_text=sage_response_text,
            sage_response_audio_url=response_audio_url,
        )

        result_dict = result.model_dump(mode="json")

        # If modification, inject instruction into session state
        if result.intent == "modification" and result.target_agent:
            mod_key = f"voice_modification_{result.target_agent}"
            tool_context.state[mod_key] = result.instruction
            logger.info(
                "Voice modification routed to %s: %s",
                result.target_agent, result.instruction,
            )

        tool_context.state["last_voice_feedback"] = result_dict
        logger.info(
            "Voice feedback processed: intent=%s, target=%s",
            result.intent, result.target_agent,
        )
        return result_dict

    except Exception as exc:
        logger.error("Failed to process voice feedback: %s", exc)
        return {
            "transcription": "",
            "intent": "question",
            "target_agent": None,
            "instruction": None,
            "sage_response_text": "I had trouble understanding that. Could you try again?",
            "sage_response_audio_url": "",
        }


# ── Internal helpers ───────────────────────────────────────────────────


def _extract_narration_context(
    milestone: str,
    tool_context: ToolContext,
) -> dict:
    """Extract context variables for narration template formatting.

    Args:
        milestone: The milestone name.
        tool_context: ADK tool context with session state.

    Returns:
        A dict of template variables.
    """
    state = tool_context.state
    context: dict = {}

    if milestone == "trend_analysis_complete":
        signals = state.get("trend_signals", [])
        context["signal_count"] = len(signals)

    elif milestone == "brand_dna_complete":
        brand_dna = state.get("brand_dna", {})
        context["brand_essence"] = brand_dna.get("brand_essence", "A unique brand identity")[:80]
        tone = brand_dna.get("tone_of_voice", "warm and authentic")
        context["tone"] = tone[:40]

    elif milestone == "production_complete":
        images = state.get("generated_images", [])
        videos = state.get("generated_videos", [])
        context["image_count"] = len(images) if isinstance(images, list) else 0
        context["video_count"] = len(videos) if isinstance(videos, list) else 0

    elif milestone == "qa_complete":
        qa_summary = state.get("qa_summary", {})
        context["score"] = f"{qa_summary.get('brand_coherence_score', 0):.0%}"
        context["violation_count"] = qa_summary.get("failed_count", 0)

    elif milestone == "campaign_complete":
        qa_summary = state.get("qa_summary", {})
        context["total_assets"] = qa_summary.get("total_assets", 0)
        context["platform_count"] = len(state.get("platforms", []))
        context["score"] = f"{qa_summary.get('brand_coherence_score', 0):.0%}"

    return context


async def _synthesize_speech(text: str) -> bytes:
    """Convert text to speech using Google Cloud TTS.

    Uses the Sage voice (en-US-Neural2-J) with default settings.

    Args:
        text: The text to synthesize.

    Returns:
        MP3 audio bytes.
    """
    try:
        from google.cloud import texttospeech

        tts_client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=SAGE_LANGUAGE_CODE,
            name=SAGE_VOICE_NAME,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0,
        )

        response = await asyncio.to_thread(
            tts_client.synthesize_speech,
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        return response.audio_content

    except Exception as exc:
        logger.warning("Cloud TTS failed, returning empty audio: %s", exc)
        return b""
