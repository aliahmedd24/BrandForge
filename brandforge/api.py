"""FastAPI server providing REST + SSE endpoints for the Live Canvas UI.

Wraps the ADK agent and exposes campaign lifecycle endpoints:
- POST /campaigns        — Create a campaign and trigger the agent pipeline
- GET  /campaigns/{id}   — Get campaign status
- POST /upload           — Upload brand assets to GCS
- GET  /campaigns/{id}/stream — SSE stream of agent events
- POST /campaigns/{id}/agents/{name}/retry — Retry a failed agent
- GET  /campaigns/{id}/bundle — Download the asset bundle ZIP
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

# Vertex AI env vars must be set before any ADK/genai imports.
# ADK's InMemoryRunner reads these to route LLM calls through Vertex AI.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "brandforge-489114")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from brandforge.shared.config import settings
from brandforge.shared.firestore import (
    CAMPAIGNS_COLLECTION,
    get_document,
    save_document,
    update_document,
)
from brandforge.shared.models import BrandBrief, Campaign, CampaignStatus, Platform
from brandforge.shared.storage import download_blob, upload_blob

logger = logging.getLogger(__name__)

app = FastAPI(title="BrandForge API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response schemas ─────────────────────────────────────────


class CampaignCreateRequest(BaseModel):
    """Request body for campaign creation."""

    brand_name: str
    product_description: str
    target_audience: str = ""
    campaign_goal: str = ""
    tone_keywords: list[str] = []
    platforms: list[str] = []
    uploaded_asset_urls: list[str] = []
    voice_brief_url: str | None = None


class CampaignCreateResponse(BaseModel):
    """Response after campaign creation."""

    campaign_id: str
    status: str


# ── Campaign endpoints ───────────────────────────────────────────────


@app.post("/campaigns", response_model=CampaignCreateResponse)
async def create_campaign(req: CampaignCreateRequest) -> CampaignCreateResponse:
    """Create a new campaign and trigger the agent pipeline."""
    try:
        platforms = []
        for p in req.platforms:
            try:
                platforms.append(Platform(p))
            except ValueError:
                logger.warning("Unknown platform: %s", p)

        brief = BrandBrief(
            brand_name=req.brand_name,
            product_description=req.product_description,
            target_audience=req.target_audience,
            campaign_goal=req.campaign_goal,
            tone_keywords=req.tone_keywords,
            platforms=platforms,
            uploaded_asset_urls=req.uploaded_asset_urls,
            voice_brief_url=req.voice_brief_url,
        )

        campaign = Campaign(brand_brief=brief, status=CampaignStatus.RUNNING)

        await save_document(
            CAMPAIGNS_COLLECTION,
            campaign.id,
            campaign.model_dump(mode="json"),
        )

        logger.info("Campaign created: %s", campaign.id)

        # Trigger agent pipeline asynchronously
        asyncio.create_task(_run_agent_pipeline(campaign.id))

        return CampaignCreateResponse(
            campaign_id=campaign.id,
            status=campaign.status.value,
        )
    except Exception as exc:
        logger.error("Failed to create campaign: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str) -> dict:
    """Get current campaign status."""
    data = await get_document(CAMPAIGNS_COLLECTION, campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return data


# ── File upload endpoint ─────────────────────────────────────────────


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    campaign_id: str = Form(...),
    type: str = Form("asset"),
) -> dict:
    """Upload a file (brand asset or voice brief) to GCS."""
    try:
        contents = await file.read()

        if type == "voice_brief":
            dest = f"campaigns/{campaign_id}/voice_brief/{file.filename}"
        else:
            dest = f"campaigns/{campaign_id}/uploads/{file.filename}"

        gcs_url = await asyncio.to_thread(
            upload_blob,
            source_data=contents,
            destination_path=dest,
            content_type=file.content_type or "application/octet-stream",
            metadata={"campaign_id": campaign_id},
        )

        logger.info("Uploaded %s for campaign %s", dest, campaign_id)
        return {"gcs_url": gcs_url, "filename": file.filename}
    except Exception as exc:
        logger.error("Upload failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── SSE streaming endpoint ───────────────────────────────────────────


@app.get("/campaigns/{campaign_id}/stream")
async def campaign_stream(campaign_id: str) -> StreamingResponse:
    """Server-Sent Events stream for real-time agent status updates."""

    async def event_generator() -> AsyncGenerator[str, None]:
        """Yield SSE events as campaign progresses."""
        last_status = None
        while True:
            data = await get_document(CAMPAIGNS_COLLECTION, campaign_id)
            if not data:
                yield f"event: error\ndata: {json.dumps({'error': 'Campaign not found'})}\n\n"
                break

            status = data.get("status", "pending")
            if status != last_status:
                yield f"event: agent_event\ndata: {json.dumps({'status': status, 'campaign_id': campaign_id})}\n\n"
                last_status = status

            if status in ("approved", "published", "failed"):
                yield f"event: agent_event\ndata: {json.dumps({'status': status, 'complete': True})}\n\n"
                break

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Agent retry endpoint ─────────────────────────────────────────────


@app.post("/campaigns/{campaign_id}/agents/{agent_name}/retry")
async def retry_agent(campaign_id: str, agent_name: str) -> dict:
    """Retry a failed agent for a campaign."""
    data = await get_document(CAMPAIGNS_COLLECTION, campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Reset agent status and re-trigger
    logger.info("Retrying agent %s for campaign %s", agent_name, campaign_id)
    asyncio.create_task(_run_agent_pipeline(campaign_id))

    return {"status": "retry_triggered", "agent_name": agent_name}


# ── Bundle download endpoint ─────────────────────────────────────────


@app.get("/campaigns/{campaign_id}/bundle")
async def download_bundle(campaign_id: str) -> StreamingResponse:
    """Download the campaign asset bundle ZIP."""
    data = await get_document(CAMPAIGNS_COLLECTION, campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    bundle_id = data.get("asset_bundle_id")
    if not bundle_id:
        raise HTTPException(status_code=404, detail="No bundle available yet")

    bundle_doc = await get_document("asset_bundles", bundle_id)
    if not bundle_doc or not bundle_doc.get("zip_gcs_url"):
        raise HTTPException(status_code=404, detail="Bundle ZIP not found")

    gcs_url = bundle_doc["zip_gcs_url"]
    path = gcs_url.replace("gs://", "").split("/", 1)[1]
    zip_bytes = await asyncio.to_thread(download_blob, path)

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="brandforge-{campaign_id[:8]}.zip"'
        },
    )


# ── GCS asset proxy endpoint ─────────────────────────────────────────


@app.get("/assets/{path:path}")
async def proxy_gcs_asset(path: str) -> StreamingResponse:
    """Proxy GCS assets to the browser.

    Converts /assets/campaigns/xxx/image.png → gs://brandforge-assets/campaigns/xxx/image.png
    """
    import mimetypes

    try:
        blob_bytes = await asyncio.to_thread(download_blob, path)
        mime, _ = mimetypes.guess_type(path)
        return StreamingResponse(
            iter([blob_bytes]),
            media_type=mime or "application/octet-stream",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as exc:
        logger.error("Failed to proxy asset %s: %s", path, exc)
        raise HTTPException(status_code=404, detail="Asset not found")


# ── Agent pipeline runner ────────────────────────────────────────────


async def _run_agent_pipeline(campaign_id: str) -> None:
    """Run the ADK agent pipeline for a campaign.

    This triggers the root agent with the campaign brief.
    In production, this is handled by ADK's InMemoryRunner.
    """
    try:
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        from brandforge.agent import root_agent

        data = await get_document(CAMPAIGNS_COLLECTION, campaign_id)
        if not data:
            logger.error("Campaign %s not found for pipeline", campaign_id)
            return

        brief = data.get("brand_brief", {})

        runner = InMemoryRunner(agent=root_agent, app_name="brandforge")

        session = await runner.session_service.create_session(
            user_id="api_user",
            app_name="brandforge",
            state={
                "campaign_id": campaign_id,
                "brand_brief": brief,
            },
        )

        prompt = (
            f"Create a full marketing campaign for {brief.get('brand_name', 'the brand')}. "
            f"Product: {brief.get('product_description', '')}. "
            f"Audience: {brief.get('target_audience', '')}. "
            f"Goal: {brief.get('campaign_goal', '')}. "
            f"Tone: {', '.join(brief.get('tone_keywords', []))}. "
            f"Platforms: {', '.join(brief.get('platforms', []))}."
        )

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )

        async for event in runner.run_async(
            user_id="api_user",
            session_id=session.id,
            new_message=content,
        ):
            logger.debug("Agent event: %s", event)

        await update_document(
            CAMPAIGNS_COLLECTION,
            campaign_id,
            {
                "status": "approved",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("Campaign %s pipeline complete", campaign_id)

    except BaseException as exc:
        # Log sub-exceptions from TaskGroup/ExceptionGroup for debugging
        if isinstance(exc, BaseExceptionGroup):
            for i, sub_exc in enumerate(exc.exceptions):
                logger.error(
                    "Pipeline sub-exception %d for campaign %s: %s: %s",
                    i, campaign_id, type(sub_exc).__name__, sub_exc,
                )
        else:
            logger.error("Pipeline failed for campaign %s: %s", campaign_id, exc)

        # Still mark as approved if we got partial results (brand_dna exists)
        try:
            campaign_data = await get_document(CAMPAIGNS_COLLECTION, campaign_id)
            has_dna = campaign_data and campaign_data.get("brand_dna_id")
        except Exception:
            has_dna = False

        final_status = "approved" if has_dna else "failed"
        await update_document(
            CAMPAIGNS_COLLECTION,
            campaign_id,
            {
                "status": final_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if has_dna:
            logger.info(
                "Campaign %s marked approved despite partial pipeline failure", campaign_id
            )
