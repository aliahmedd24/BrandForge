#!/usr/bin/env bash
# BrandForge — Seed Secrets Script
# Populates Google Secret Manager with required API keys.
#
# Usage:
#   export GCP_PROJECT_ID=brandforge-489114
#   ./scripts/seed_secrets.sh
#
# This script prompts for secrets interactively — never pass them as CLI args.

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-brandforge-489114}"

echo "🔐 BrandForge Secret Seeding — Project: ${PROJECT_ID}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

gcloud config set project "${PROJECT_ID}"

# Helper to create or update a secret
seed_secret() {
    local secret_name="$1"
    local prompt_msg="$2"

    echo ""
    read -rsp "Enter ${prompt_msg}: " secret_value
    echo ""

    if [ -z "${secret_value}" ]; then
        echo "   ⏭️  Skipped ${secret_name} (empty input)"
        return
    fi

    # Create the secret if it doesn't exist
    if ! gcloud secrets describe "${secret_name}" --quiet 2>/dev/null; then
        gcloud secrets create "${secret_name}" \
            --replication-policy="automatic" \
            --quiet
        echo "   Created secret: ${secret_name}"
    fi

    # Add the new version
    echo -n "${secret_value}" | gcloud secrets versions add "${secret_name}" \
        --data-file=- --quiet
    echo "   ✅ ${secret_name} — version added"
}

# ── Required Secrets ───────────────────────────────────────────────────────
seed_secret "GEMINI_API_KEY" "Gemini API Key"

# ── Future Phase Secrets (optional — skip with Enter) ──────────────────────
echo ""
echo "The following secrets are needed in later phases. Press Enter to skip."
seed_secret "INSTAGRAM_MCP_TOKEN" "Instagram MCP Token (Phase 5)"
seed_secret "LINKEDIN_MCP_TOKEN" "LinkedIn MCP Token (Phase 5)"
seed_secret "TIKTOK_MCP_TOKEN" "TikTok MCP Token (Phase 5)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Secret seeding complete!"
echo ""
echo "Verify with: gcloud secrets list --project=${PROJECT_ID}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
