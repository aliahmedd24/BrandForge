"""FunctionTool implementations for the Trend Injector Agent.

Uses Gemini with Google Search grounding to research real-time platform
trends, audience hooks, and cultural moments. All results include source
URLs for grounding evidence.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.adk.tools import ToolContext
from google.genai import types

from brandforge.agents.trend_injector.prompts import (
    HOOK_RESEARCH_PROMPT,
    TREND_RESEARCH_SYSTEM_PROMPT,
)
from brandforge.shared.config import get_vertexai_config, settings
from brandforge.shared.firestore import TREND_BRIEFS_COLLECTION, save_document
from brandforge.shared.models import TrendBrief, TrendSignal

logger = logging.getLogger(__name__)

AGENT_MODEL = "gemini-2.0-flash"

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


# ── Tool 1: Research Platform Trends ───────────────────────────────────


async def research_platform_trends(
    platforms: str,
    industry: str,
    audience: str,
    tool_context: ToolContext,
) -> list[dict]:
    """Research trending content formats and cultural moments per platform.

    Uses Gemini with Google Search grounding to find real-time trends.
    Scoped to content from the past 30 days only.

    Args:
        platforms: Comma-separated platform names (e.g. "instagram,tiktok").
        industry: The brand's industry category (e.g. "sustainable fashion").
        audience: Target audience description.

    Returns:
        A list of TrendSignal dicts with source URLs.
    """
    try:
        platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
        now = datetime.now(timezone.utc)
        current_month = now.strftime("%B %Y")

        search_queries = []
        for platform in platform_list:
            search_queries.extend([
                f"{platform} trending content formats {current_month}",
                f"{industry} viral ads {now.year}",
                f"top performing {platform} hooks for {audience} {current_month}",
            ])

        query_text = (
            f"Research the following queries and extract trend signals:\n"
            + "\n".join(f"- {q}" for q in search_queries)
            + f"\n\nIndustry: {industry}\nAudience: {audience}\n"
            f"Only include trends from the past 30 days."
        )

        logger.info("Researching platform trends for %s", platform_list)
        client = _get_genai_client()

        # Use Google Search grounding tool
        google_search_tool = types.Tool(google_search=types.GoogleSearch())

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=query_text,
            config=types.GenerateContentConfig(
                system_instruction=TREND_RESEARCH_SYSTEM_PROMPT,
                tools=[google_search_tool],
                response_mime_type="application/json",
            ),
        )

        raw = json.loads(response.text)
        signals_raw = raw if isinstance(raw, list) else raw.get("signals", [])

        signals = []
        for item in signals_raw[:8]:
            try:
                signal = TrendSignal.model_validate(item)
                # Only include signals with source URLs (grounding proof)
                if signal.source_url and signal.confidence > 0:
                    signals.append(signal.model_dump(mode="json"))
            except Exception as val_exc:
                logger.warning("Skipping invalid trend signal: %s", val_exc)

        tool_context.state["trend_signals"] = signals
        tool_context.state["search_queries_used"] = search_queries
        logger.info("Found %d trend signals", len(signals))
        return signals

    except asyncio.TimeoutError:
        logger.warning("Trend research timed out, proceeding without trends")
        tool_context.state["trend_signals"] = []
        tool_context.state["search_queries_used"] = []
        return []
    except Exception as exc:
        logger.error("Failed to research platform trends: %s", exc)
        tool_context.state["trend_signals"] = []
        tool_context.state["search_queries_used"] = []
        return []


# ── Tool 2: Research Audience Hooks ────────────────────────────────────


async def research_audience_hooks(
    audience_description: str,
    platforms: str,
    tool_context: ToolContext,
) -> list[str]:
    """Research proven opening hooks for the target audience.

    Uses Gemini with Google Search grounding to find hook patterns
    that resonate with the specified demographic.

    Args:
        audience_description: Description of the target audience.
        platforms: Comma-separated platform names.

    Returns:
        A list of 3-5 hook pattern strings.
    """
    try:
        prompt = HOOK_RESEARCH_PROMPT.format(
            audience_description=audience_description,
            platforms=platforms,
        )

        logger.info("Researching audience hooks for: %s", audience_description[:50])
        client = _get_genai_client()

        google_search_tool = types.Tool(google_search=types.GoogleSearch())

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=AGENT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[google_search_tool],
                response_mime_type="application/json",
            ),
        )

        raw = json.loads(response.text)
        hooks = raw if isinstance(raw, list) else raw.get("hooks", [])
        hooks = [str(h) for h in hooks[:5]]

        tool_context.state["hook_patterns"] = hooks
        logger.info("Found %d audience hooks", len(hooks))
        return hooks

    except Exception as exc:
        logger.error("Failed to research audience hooks: %s", exc)
        tool_context.state["hook_patterns"] = []
        return []


# ── Tool 3: Compile Trend Brief ────────────────────────────────────────


async def compile_trend_brief(
    campaign_id: str,
    tool_context: ToolContext,
) -> dict:
    """Synthesize trend signals and hooks into a structured TrendBrief.

    Reads trend_signals, hook_patterns, and search_queries_used from
    session state. Stores the compiled brief in Firestore.

    Args:
        campaign_id: The campaign this trend brief belongs to.

    Returns:
        A dict representation of the TrendBrief.
    """
    real_campaign_id = tool_context.state.get("campaign_id", campaign_id)

    try:
        signals_raw = tool_context.state.get("trend_signals", [])
        hooks = tool_context.state.get("hook_patterns", [])
        search_queries = tool_context.state.get("search_queries_used", [])

        signals = [TrendSignal.model_validate(s) for s in signals_raw]

        # Build platform format recommendations from signals
        platform_recs: dict[str, str] = {}
        for signal in signals:
            if signal.platform and signal.category == "format":
                platform_recs.setdefault(
                    signal.platform.value,
                    signal.description[:100],
                )

        # Build cultural context summary
        cultural_signals = [s for s in signals if s.category == "cultural"]
        cultural_context = (
            ". ".join(s.description for s in cultural_signals[:3])
            if cultural_signals
            else "No significant cultural moments detected for this campaign context."
        )

        # Generate the TrendBrief using Gemini to synthesize
        client = _get_genai_client()
        synthesis_prompt = (
            f"Given these trend signals:\n{json.dumps(signals_raw, indent=2)}\n\n"
            f"And these hooks:\n{json.dumps(hooks)}\n\n"
            f"Write a 2-3 sentence cultural context paragraph summarizing the current "
            f"cultural mood relevant to a campaign targeting these trends."
        )

        try:
            synthesis_response = await asyncio.to_thread(
                client.models.generate_content,
                model=AGENT_MODEL,
                contents=synthesis_prompt,
            )
            cultural_context = synthesis_response.text.strip()
        except Exception:
            pass  # Keep the rule-based cultural context

        trend_brief = TrendBrief(
            campaign_id=real_campaign_id,
            signals=signals,
            platform_format_recommendations=platform_recs,
            hook_patterns=hooks,
            cultural_context=cultural_context,
            search_queries_used=search_queries,
        )

        brief_dict = trend_brief.model_dump(mode="json")

        # Store in Firestore
        try:
            await save_document(
                TREND_BRIEFS_COLLECTION, trend_brief.id, brief_dict
            )
            logger.info("Trend brief stored (id=%s)", trend_brief.id)
        except Exception as store_exc:
            logger.warning("Failed to store trend brief: %s", store_exc)

        # Inject into session state for Brand Strategist
        tool_context.state["trend_brief"] = brief_dict
        logger.info(
            "Trend brief compiled for campaign %s: %d signals, %d hooks",
            real_campaign_id, len(signals), len(hooks),
        )
        return brief_dict

    except Exception as exc:
        logger.error("Failed to compile trend brief: %s", exc)
        # Graceful fallback: empty trend brief
        fallback = TrendBrief(
            campaign_id=real_campaign_id,
            signals=[],
            platform_format_recommendations={},
            hook_patterns=[],
            cultural_context="Trend research unavailable for this campaign.",
            search_queries_used=[],
        )
        fallback_dict = fallback.model_dump(mode="json")
        tool_context.state["trend_brief"] = fallback_dict
        return fallback_dict
