import useCampaignStore from "../../stores/campaignStore";
import AgentNode from "./AgentNode";
import { retryAgent } from "../../lib/api";

const PIPELINE_ORDER = [
  "brandforge_root",
  "brand_strategist",
  "production_orchestrator",
  "scriptwriter",
  "mood_board_director",
  "image_generator",
  "video_producer",
  "copy_editor",
  "qa_orchestrator",
  "brand_qa_inspector",
  "campaign_assembler",
];

export default function AgentPipeline() {
  const agentStatuses = useCampaignStore((s) => s.agentStatuses);
  const campaignId = useCampaignStore((s) => s.campaignId);

  const handleRetry = async (agentName) => {
    if (campaignId) {
      await retryAgent(campaignId, agentName);
    }
  };

  return (
    <aside className="glass-panel p-4 space-y-1 overflow-y-auto" aria-label="Agent pipeline status">
      <h2 className="text-xs font-semibold text-brand-muted uppercase tracking-wider mb-3">
        Agent Pipeline
      </h2>
      {PIPELINE_ORDER.map((name) => (
        <AgentNode
          key={name}
          name={name}
          status={agentStatuses[name] || "idle"}
          onRetry={handleRetry}
        />
      ))}
    </aside>
  );
}
