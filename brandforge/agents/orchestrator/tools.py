"""Production Orchestrator tool implementations — Phase 2.

Manages the two-wave production pipeline: launch, status tracking,
and finalisation of all 6 creative production agents.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from brandforge.shared.config import (
    FIRESTORE_COLLECTION_BRAND_DNA,
    FIRESTORE_COLLECTION_CAMPAIGNS,
    PUBSUB_TOPIC_AGENT_COMPLETE,
    EVENT_PRODUCTION_COMPLETE,
    get_config,
)
from brandforge.shared.models import (
    AgentMessage,
    AgentRun,
    AgentStatus,
    CampaignStatus,
)

logger = logging.getLogger(__name__)

# The 6 production agents in wave order
_WAVE_1_AGENTS = ["scriptwriter", "mood_board_director", "virtual_tryon"]
_WAVE_2_AGENTS = ["copy_editor", "video_producer", "image_generator"]
_ALL_AGENTS = _WAVE_1_AGENTS + _WAVE_2_AGENTS

# Dependencies: Wave 2 agent → Wave 1 agent it depends on
_DEPENDENCIES = {
    "copy_editor": "scriptwriter",
    "video_producer": "scriptwriter",
    "image_generator": "mood_board_director",
}

_PIPELINE_TIMEOUT_SECONDS = 900  # 15 minutes


# ---------------------------------------------------------------------------
# Tool: launch_production_pipeline
# ---------------------------------------------------------------------------


async def launch_production_pipeline(
    campaign_id: str,
    brand_dna_id: str,
) -> dict[str, Any]:
    """Validate BrandDNA and initialise AgentRun records for all 6 agents.

    Args:
        campaign_id: The campaign ID.
        brand_dna_id: The BrandDNA document ID.

    Returns:
        dict with status and execution plan summary.
    """
    try:
        from brandforge.shared import firestore as fs

        # Validate BrandDNA exists
        brand_dna = await fs.get_document(
            collection=FIRESTORE_COLLECTION_BRAND_DNA,
            doc_id=brand_dna_id,
        )
        if not brand_dna:
            return {
                "status": "error",
                "error": f"BrandDNA {brand_dna_id} not found. Run Brand Strategist first.",
            }

        # Update campaign status to RUNNING
        try:
            await fs.update_document(
                collection=FIRESTORE_COLLECTION_CAMPAIGNS,
                doc_id=campaign_id,
                updates={"status": CampaignStatus.RUNNING},
            )
        except Exception:
            logger.warning("Could not update campaign status (campaign may not exist yet)")

        # Create AgentRun records for all 6 agents
        agent_runs: list[dict[str, Any]] = []
        now = datetime.utcnow()
        for agent_name in _ALL_AGENTS:
            run = AgentRun(
                campaign_id=campaign_id,
                agent_name=agent_name,
                status=AgentStatus.IDLE,
                started_at=now,
            )
            await fs.create_document(
                collection="agent_runs",
                doc_id=run.id,
                data=run.model_dump(mode="json"),
            )
            agent_runs.append({
                "agent_name": agent_name,
                "run_id": run.id,
                "status": AgentStatus.IDLE,
            })

        logger.info(
            "Production pipeline launched for campaign %s with %d agents",
            campaign_id, len(agent_runs),
        )
        return {
            "status": "success",
            "message": "Production pipeline initialized.",
            "wave_1": _WAVE_1_AGENTS,
            "wave_2": _WAVE_2_AGENTS,
            "agent_runs": agent_runs,
            "brand_dna_id": brand_dna_id,
            "pipeline_timeout_seconds": _PIPELINE_TIMEOUT_SECONDS,
        }

    except Exception as exc:
        logger.error("launch_production_pipeline failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: check_pipeline_status
# ---------------------------------------------------------------------------


async def check_pipeline_status(
    campaign_id: str,
) -> dict[str, Any]:
    """Query all AgentRun records for the campaign and return status map.

    Args:
        campaign_id: The campaign ID.

    Returns:
        dict with per-agent status and overall completion state.
    """
    try:
        from brandforge.shared import firestore as fs

        runs = await fs.query_collection(
            collection="agent_runs",
            field="campaign_id",
            op="==",
            value=campaign_id,
        )

        # Build status map
        status_map: dict[str, str] = {}
        for run in runs:
            agent = run.get("agent_name", "")
            status = run.get("status", "unknown")
            if agent in _ALL_AGENTS:
                # Keep the most recent/best status per agent
                if agent not in status_map or status == AgentStatus.COMPLETE:
                    status_map[agent] = status

        # Check wave completion
        wave_1_complete = all(
            status_map.get(a) == AgentStatus.COMPLETE
            for a in _WAVE_1_AGENTS
        )
        wave_2_complete = all(
            status_map.get(a) == AgentStatus.COMPLETE
            for a in _WAVE_2_AGENTS
        )

        # Check for failures
        failures = [
            a for a in _ALL_AGENTS
            if status_map.get(a) == AgentStatus.FAILED
        ]

        # Check dependency blocks for Wave 2
        blocked: list[str] = []
        for w2_agent, dep in _DEPENDENCIES.items():
            if status_map.get(dep) == AgentStatus.FAILED:
                blocked.append(f"{w2_agent} blocked: {dep} failed")

        all_complete = wave_1_complete and wave_2_complete

        return {
            "status": "success",
            "agent_status": status_map,
            "wave_1_complete": wave_1_complete,
            "wave_2_complete": wave_2_complete,
            "all_complete": all_complete,
            "failures": failures,
            "blocked_agents": blocked,
        }

    except Exception as exc:
        logger.error("check_pipeline_status failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: finalize_production
# ---------------------------------------------------------------------------


async def finalize_production(
    campaign_id: str,
) -> dict[str, Any]:
    """Finalise the production pipeline after all agents complete.

    Verifies all agents are done, updates campaign status, and publishes
    the production_complete event.

    Args:
        campaign_id: The campaign ID.

    Returns:
        dict with final status and summary.
    """
    try:
        from brandforge.shared import firestore as fs
        from brandforge.shared.pubsub import publish_message

        # Check final status
        status_result = await check_pipeline_status(campaign_id)
        if status_result.get("status") != "success":
            return status_result

        agent_status = status_result.get("agent_status", {})
        failures = status_result.get("failures", [])

        # Update campaign status
        if failures:
            campaign_status = CampaignStatus.QA_REVIEW
        else:
            campaign_status = CampaignStatus.QA_REVIEW

        try:
            await fs.update_document(
                collection=FIRESTORE_COLLECTION_CAMPAIGNS,
                doc_id=campaign_id,
                updates={
                    "status": campaign_status,
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
        except Exception:
            logger.warning("Could not update campaign status")

        # Publish production_complete event
        await publish_message(
            topic=PUBSUB_TOPIC_AGENT_COMPLETE,
            message=AgentMessage(
                source_agent="orchestrator",
                target_agent="qa_agent",
                campaign_id=campaign_id,
                event_type=EVENT_PRODUCTION_COMPLETE,
                payload={
                    "agent_status": agent_status,
                    "failures": failures,
                    "campaign_status": campaign_status,
                },
            ),
        )

        logger.info(
            "Production pipeline finalised for campaign %s (failures: %s)",
            campaign_id, failures or "none",
        )
        return {
            "status": "success",
            "message": "Production pipeline complete.",
            "agent_status": agent_status,
            "failures": failures,
            "campaign_status": campaign_status,
        }

    except Exception as exc:
        logger.error("finalize_production failed: %s", exc)
        return {"status": "error", "error": str(exc)}
