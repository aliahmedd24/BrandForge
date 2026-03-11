import { useEffect } from "react";
import useCampaignStore from "../stores/campaignStore";

export default function useCampaignListener(campaignId) {
  const subscribe = useCampaignStore((s) => s.subscribeToCampaign);
  const cleanup = useCampaignStore((s) => s.cleanup);

  useEffect(() => {
    if (!campaignId) return;
    subscribe(campaignId);
    return () => cleanup();
  }, [campaignId, subscribe, cleanup]);
}
