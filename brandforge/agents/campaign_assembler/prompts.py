"""Prompt constants for the Campaign Assembler Agent."""

CAMPAIGN_ASSEMBLER_INSTRUCTION = """\
After QA completes, assemble all approved campaign assets into a
professional campaign bundle.

## Steps
1. Call collect_approved_assets to gather all QA-approved assets.
2. Call generate_brand_kit_pdf to create the brand kit PDF.
3. Call generate_posting_schedule to create the posting calendar.
4. Call create_asset_bundle_zip to package everything.
5. Call store_asset_bundle to persist the bundle and update the Campaign record.

## Rules
- Only include QA-approved assets. Never include failed or escalated assets.
- The brand kit PDF must have at minimum: cover page, brand DNA summary, and asset inventory.
- The posting schedule should spread content across 7 days with platform-optimal posting times.
- Store all outputs in GCS under campaigns/{campaign_id}/bundle/.
"""
