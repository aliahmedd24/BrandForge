"""Demo mode constants for hackathon presentation.

Pre-scripted brand brief and sabotage prompt for reliable QA failure
demonstration during the 5-minute hackathon demo.
"""

from brandforge.shared.models import BrandBrief, Platform

DEMO_BRIEF = BrandBrief(
    brand_name="Grounded",
    product_description=(
        "Premium sustainable sneakers made from recycled ocean plastic "
        "and natural rubber. Handcrafted in Portugal with zero-waste "
        "manufacturing. Price point: $185."
    ),
    target_audience=(
        "Urban eco-conscious millennials (25-35) who value authenticity, "
        "sustainability, and understated luxury. Heavy Instagram and "
        "TikTok users."
    ),
    campaign_goal="product launch",
    tone_keywords=["earthy", "bold", "sustainable", "urban", "authentic"],
    platforms=[Platform.INSTAGRAM, Platform.TIKTOK, Platform.LINKEDIN],
    uploaded_asset_urls=[],
    voice_brief_url=None,
)

DEMO_SABOTAGE_PROMPT = (
    "icy blue-steel palette, metallic gray tones, cool blue lighting, "
    "cold industrial aesthetic, chrome and steel surfaces"
)
