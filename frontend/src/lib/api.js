const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export async function createCampaign(brief) {
  const res = await fetch(`${API_BASE}/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(brief),
  });

  if (!res.ok) throw new Error(`Failed to create campaign: ${res.statusText}`);
  return res.json();
}

export async function createDemoCampaign() {
  const res = await fetch(`${API_BASE}/campaigns/demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) throw new Error(`Failed to create demo campaign: ${res.statusText}`);
  return res.json();
}

export async function fetchInfraStatus() {
  const res = await fetch(`${API_BASE}/infra/status`);
  if (!res.ok) throw new Error(`Failed to fetch infra status: ${res.statusText}`);
  return res.json();
}

export async function getCampaignStatus(campaignId) {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}`);
  if (!res.ok) throw new Error(`Failed to get campaign: ${res.statusText}`);
  return res.json();
}

export function createSSEConnection(campaignId) {
  return new EventSource(`${API_BASE}/campaigns/${campaignId}/stream`);
}

export async function retryAgent(campaignId, agentName) {
  const res = await fetch(
    `${API_BASE}/campaigns/${campaignId}/agents/${agentName}/retry`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`Failed to retry agent: ${res.statusText}`);
  return res.json();
}

export async function downloadBundle(campaignId) {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/bundle`);
  if (!res.ok) throw new Error(`Failed to download bundle: ${res.statusText}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `brandforge-campaign-${campaignId}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}
