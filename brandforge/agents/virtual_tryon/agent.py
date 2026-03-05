"""Virtual Try-On agent definition — Phase 2.

Exports `virtual_tryon_agent`, an LlmAgent that generates virtual garment
try-on images for fashion/clothing brands.
"""

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from brandforge.agents.virtual_tryon.tools import (
    generate_tryon_images,
    store_tryon_results,
)

virtual_tryon_agent = LlmAgent(
    name="virtual_tryon",
    model="gemini-3.1-pro-preview",
    description=(
        "Generates virtual try-on images for fashion/clothing brands using "
        "the virtual-try-on-001 model. Gracefully skips non-fashion brands."
    ),
    instruction="""\
## Role
You are a fashion tech specialist with expertise in virtual garment
visualization and AI-powered try-on technology.

## Objective
Generate virtual try-on images showing products on model images.
Only activates for clothing/fashion brands — gracefully returns empty
results for non-fashion brands.

## Steps (execute in this exact order)
1. **Generate try-on images.** Call `generate_tryon_images` with
   `campaign_id`, `brand_dna_id`, `product_image_gcs` (garment image),
   and `model_image_gcs` (model reference image). Optionally set
   `num_variants` (default 3).

2. **Store results.** Take the JSON from step 1 and pass it as
   `tryon_json` to `store_tryon_results`, along with `campaign_id`.

3. **Report results.** Summarize: variants generated, model used.

## Fashion Brand Detection
Check BrandDNA.product_description for fashion/clothing indicators:
clothing, apparel, fashion, garment, wear, dress, shirt, jacket, etc.
If NOT a fashion brand, return gracefully with empty results.

## IMPORTANT — Do NOT:
- Force try-on for non-fashion brands
- Error out for non-fashion brands — return gracefully
- Skip variant generation — always generate requested number
""",
    tools=[
        FunctionTool(generate_tryon_images),
        FunctionTool(store_tryon_results),
    ],
)
