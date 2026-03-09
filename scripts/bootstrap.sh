#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# BrandForge — GCP Infrastructure Bootstrap
#
# Provisions all required GCP services for BrandForge.
# Idempotent: safe to run multiple times.
#
# Usage:
#   export GOOGLE_CLOUD_PROJECT=your-project-id
#   bash scripts/bootstrap.sh
# ──────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT env var}"
REGION="${BRANDFORGE_GCP_REGION:-us-central1}"
BUCKET="${BRANDFORGE_GCS_BUCKET:-brandforge-assets}"
AR_REPO="${BRANDFORGE_AR_REPO:-brandforge-repo}"
PUBSUB_TOPIC_CREATED="brandforge.campaign.created"
PUBSUB_TOPIC_PUBLISHED="brandforge.campaign.published"

echo "========================================="
echo "BrandForge Bootstrap"
echo "  Project:  ${PROJECT}"
echo "  Region:   ${REGION}"
echo "  Bucket:   ${BUCKET}"
echo "========================================="

# ── Set active project ──────────────────────────────────────────────────

gcloud config set project "${PROJECT}"

# ── Enable required APIs ────────────────────────────────────────────────

echo ""
echo ">>> Enabling APIs..."
gcloud services enable \
    aiplatform.googleapis.com \
    firestore.googleapis.com \
    storage.googleapis.com \
    pubsub.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    cloudresourcemanager.googleapis.com \
    generativelanguage.googleapis.com

echo "    APIs enabled."

# ── Firestore (Native mode) ─────────────────────────────────────────────

echo ""
echo ">>> Provisioning Firestore (Native mode)..."
if gcloud firestore databases describe --database="(default)" --project="${PROJECT}" >/dev/null 2>&1; then
    echo "    Firestore database already exists."
else
    gcloud firestore databases create \
        --location="${REGION}" \
        --type=firestore-native \
        --project="${PROJECT}"
    echo "    Firestore database created."
fi

# ── Cloud Storage bucket ────────────────────────────────────────────────

echo ""
echo ">>> Provisioning GCS bucket..."
if gsutil ls -b "gs://${BUCKET}" >/dev/null 2>&1; then
    echo "    Bucket gs://${BUCKET} already exists."
else
    gsutil mb -p "${PROJECT}" -l "${REGION}" -b on "gs://${BUCKET}"
    echo "    Bucket gs://${BUCKET} created."
fi

# ── Pub/Sub topics ───────────────────────────────────────────────────────

echo ""
echo ">>> Provisioning Pub/Sub topics..."
for TOPIC in "${PUBSUB_TOPIC_CREATED}" "${PUBSUB_TOPIC_PUBLISHED}"; do
    if gcloud pubsub topics describe "${TOPIC}" --project="${PROJECT}" >/dev/null 2>&1; then
        echo "    Topic ${TOPIC} already exists."
    else
        gcloud pubsub topics create "${TOPIC}" --project="${PROJECT}"
        echo "    Topic ${TOPIC} created."
    fi
done

# ── Artifact Registry ───────────────────────────────────────────────────

echo ""
echo ">>> Provisioning Artifact Registry..."
if gcloud artifacts repositories describe "${AR_REPO}" \
    --location="${REGION}" --project="${PROJECT}" >/dev/null 2>&1; then
    echo "    Repository ${AR_REPO} already exists."
else
    gcloud artifacts repositories create "${AR_REPO}" \
        --repository-format=docker \
        --location="${REGION}" \
        --project="${PROJECT}" \
        --description="BrandForge container images"
    echo "    Repository ${AR_REPO} created."
fi

# ── Done ─────────────────────────────────────────────────────────────────

echo ""
echo "========================================="
echo "Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Run: bash scripts/seed_secrets.sh"
echo "  2. Run: uv sync"
echo "  3. Run: adk web brandforge"
echo "========================================="
