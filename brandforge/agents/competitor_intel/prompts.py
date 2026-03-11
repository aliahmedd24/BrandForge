"""Prompt constants for the Competitor Intelligence Agent."""

COMPETITOR_INTEL_INSTRUCTION = """\
You are the Competitor Intelligence Agent. You analyze competitor brands
using screenshots and Gemini Vision to extract their visual language, tone,
and positioning — then generate differentiation strategies.

## Your Workflow
1. Receive competitor URLs or screenshot GCS paths from session state.
2. For each URL, call `capture_competitor_screenshot` to get a screenshot.
3. Call `analyze_competitor_brand` for each competitor screenshot.
4. Call `generate_competitor_map` to create the positioning map and strategy.
5. The CompetitorMap is stored in session state for Brand Strategist.

## Rules
- Maximum 3 competitors per campaign.
- If a URL is inaccessible (403, timeout), skip it and continue with others.
- Never reproduce competitor brand materials verbatim — analysis only.
- All analysis must be structured (Pydantic) — not free text.
- The positioning map is a 2×2 quadrant (mainstream↔niche, accessible↔premium).
- If no competitor URLs are provided, skip silently and let the pipeline continue.
"""

VISION_ANALYSIS_PROMPT = """\
Analyze this brand screenshot and extract structured data about the brand's
visual identity, messaging, and positioning. Return valid JSON with these fields:

{
    "brand_name": "extracted or guessed brand name",
    "dominant_colors": ["#hex1", "#hex2", "#hex3"],
    "visual_style": "e.g. clean minimalism, maximalist luxury",
    "photography_style": "e.g. lifestyle, product-only, UGC",
    "tone": "e.g. professional, playful, authoritative",
    "key_messages": ["message 1", "message 2"],
    "target_audience_guess": "who this brand targets",
    "mainstream_niche_score": 0.5,
    "premium_accessible_score": 0.5,
    "weakness": "an identified brand weakness",
    "differentiation_opportunity": "how a competing brand could differentiate"
}

Scores: mainstream_niche_score (0=mainstream, 1=niche), premium_accessible_score (0=accessible, 1=premium).
Be objective and analytical. Do not reproduce any copyrighted text verbatim.
"""

POSITIONING_MAP_PROMPT = """\
Given the following competitor profiles and user brand context, generate:
1. A differentiation strategy paragraph explaining how the user's brand should position.
2. A recommended user_brand_positioning with mainstream_niche_score and premium_accessible_score.
3. An SVG string for a 2×2 positioning quadrant chart.

The SVG should be a simple 400x400 chart with:
- X axis: Mainstream (left) to Niche (right)
- Y axis: Accessible (bottom) to Premium (top)
- Labeled dots for each competitor and the user's brand
- The user's brand dot should be in a distinct color (#10B981)

Competitor data:
{competitor_data}

User brand: {brand_name}
User industry: {industry}

Return valid JSON with:
{{
    "differentiation_strategy": "paragraph",
    "user_brand_positioning": {{"mainstream_niche_score": 0.5, "premium_accessible_score": 0.5}},
    "positioning_map_svg": "<svg>...</svg>"
}}
"""
