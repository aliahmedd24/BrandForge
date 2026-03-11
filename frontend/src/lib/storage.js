const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export async function uploadAsset(file, campaignId) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("campaign_id", campaignId);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export async function uploadVoiceBrief(blob, campaignId) {
  const formData = new FormData();
  formData.append("file", blob, "voice_brief.webm");
  formData.append("campaign_id", campaignId);
  formData.append("type", "voice_brief");

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) throw new Error(`Voice upload failed: ${res.statusText}`);
  return res.json();
}

export function getSignedUrl(gcsUrl) {
  if (!gcsUrl) return "";
  if (gcsUrl.startsWith("http")) return gcsUrl;
  // Strip gs://bucket-name/ prefix to get the blob path
  const path = gcsUrl.replace("gs://", "").replace(/^[^/]+\//, "");
  return `${API_BASE}/assets/${path}`;
}
