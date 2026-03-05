#!/usr/bin/env bash
# BrandForge — GCP Bootstrap Script
# Provisions all required GCP services for the project.
# Idempotent: safe to re-run without side effects.
#
# Usage:
#   export GCP_PROJECT_ID=brandforge-489114
#   ./scripts/bootstrap.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - Billing enabled on the GCP project

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-brandforge-489114}"
REGION="${GCP_REGION:-us-central1}"
BUCKET_NAME="${GCS_BUCKET_NAME:-brandforge-assets}"
AR_REPO="brandforge-images"

echo "🚀 BrandForge Bootstrap — Project: ${PROJECT_ID}, Region: ${REGION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Set active project ─────────────────────────────────────────────────────
echo "📌 Setting active project..."
gcloud config set project "${PROJECT_ID}"

# ── Enable APIs ────────────────────────────────────────────────────────────
echo "🔌 Enabling required APIs..."
gcloud services enable \
    firestore.googleapis.com \
    storage.googleapis.com \
    pubsub.googleapis.com \
    secretmanager.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    --quiet

echo "✅ APIs enabled"

# ── Firestore (Native mode) ───────────────────────────────────────────────
echo "🔥 Provisioning Firestore (Native mode)..."
if gcloud firestore databases describe --quiet 2>/dev/null; then
    echo "   Firestore already exists — skipping"
else
    gcloud firestore databases create \
        --location="${REGION}" \
        --type=firestore-native \
        --quiet
    echo "   ✅ Firestore created in Native mode"
fi

# ── GCS Bucket ─────────────────────────────────────────────────────────────
echo "🪣 Creating GCS bucket: gs://${BUCKET_NAME}"
if gsutil ls -b "gs://${BUCKET_NAME}" 2>/dev/null; then
    echo "   Bucket already exists — skipping"
else
    gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET_NAME}"
    gsutil uniformbucketlevelaccess set on "gs://${BUCKET_NAME}"
    echo "   ✅ Bucket created with uniform access"
fi

# ── Pub/Sub Topics ─────────────────────────────────────────────────────────
echo "📬 Creating Pub/Sub topics..."
TOPICS=(
    "brandforge.campaign.created"
    "brandforge.agent.complete"
    "brandforge.qa.failed"
    "brandforge.campaign.published"
    "brandforge.analytics.insights"
)
for topic in "${TOPICS[@]}"; do
    if gcloud pubsub topics describe "${topic}" --quiet 2>/dev/null; then
        echo "   ${topic} — already exists"
    else
        gcloud pubsub topics create "${topic}" --quiet
        echo "   ✅ Created topic: ${topic}"
    fi
done

# ── Artifact Registry ─────────────────────────────────────────────────────
echo "📦 Creating Artifact Registry repository..."
if gcloud artifacts repositories describe "${AR_REPO}" \
    --location="${REGION}" --quiet 2>/dev/null; then
    echo "   Repository already exists — skipping"
else
    gcloud artifacts repositories create "${AR_REPO}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="BrandForge container images" \
        --quiet
    echo "   ✅ Artifact Registry repository created"
fi

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ BrandForge bootstrap complete!"
echo ""
echo "   Project:    ${PROJECT_ID}"
echo "   Region:     ${REGION}"
echo "   Firestore:  Native mode"
echo "   Bucket:     gs://${BUCKET_NAME}"
echo "   Topics:     ${#TOPICS[@]} Pub/Sub topics"
echo "   Registry:   ${AR_REPO}"
echo ""
echo "Next steps:"
echo "   1. Run ./scripts/seed_secrets.sh to populate Secret Manager"
echo "   2. Run pytest tests/infra/ to validate connectivity"
echo "   3. Run adk web to start the local dev server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
