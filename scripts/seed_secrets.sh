#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# BrandForge — Secret Manager Seed Script
#
# Populates Google Secret Manager with required API keys.
# Prompts interactively for each secret value.
#
# Usage:
#   export GOOGLE_CLOUD_PROJECT=your-project-id
#   bash scripts/seed_secrets.sh
# ──────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT env var}"

echo "========================================="
echo "BrandForge — Seed Secrets"
echo "  Project: ${PROJECT}"
echo "========================================="

# Helper: create or update a secret
seed_secret() {
    local SECRET_ID="$1"
    local PROMPT_MSG="$2"

    echo ""
    read -r -s -p "${PROMPT_MSG}: " SECRET_VALUE
    echo ""

    if [ -z "${SECRET_VALUE}" ]; then
        echo "    Skipped ${SECRET_ID} (empty value)."
        return
    fi

    # Create the secret if it doesn't exist
    if ! gcloud secrets describe "${SECRET_ID}" --project="${PROJECT}" >/dev/null 2>&1; then
        gcloud secrets create "${SECRET_ID}" \
            --replication-policy="automatic" \
            --project="${PROJECT}"
        echo "    Created secret ${SECRET_ID}."
    fi

    # Add a new version with the value
    echo -n "${SECRET_VALUE}" | gcloud secrets versions add "${SECRET_ID}" \
        --data-file=- \
        --project="${PROJECT}"
    echo "    Secret ${SECRET_ID} version added."
}

# ── Seed required secrets ────────────────────────────────────────────────
# All AI model calls use Vertex AI with Application Default Credentials.
# Add any additional application secrets below as needed.

echo ""
echo "========================================="
echo "No API key secrets needed — using Vertex AI with ADC."
echo ""
echo "Ensure you have authenticated:"
echo "  gcloud auth application-default login"
echo "========================================="
