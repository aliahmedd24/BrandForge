import { useParams } from "react-router-dom";
import { Sparkles } from "lucide-react";
import useCampaignListener from "../hooks/useCampaignListener";
import useCampaignStore from "../stores/campaignStore";
import AgentPipeline from "../components/canvas/AgentPipeline";
import GenerativeFeed from "../components/canvas/GenerativeFeed";
import BrandDNAViewer from "../components/canvas/BrandDNAViewer";
import BrandCoherenceScore from "../components/canvas/BrandCoherenceScore";
import CampaignComplete from "../components/canvas/CampaignComplete";

export default function CanvasPage() {
  const { campaignId } = useParams();
  useCampaignListener(campaignId);

  const status = useCampaignStore((s) => s.status);

  const isComplete = status === "approved" || status === "published";

  return (
    <div className="h-screen flex flex-col">
      {/* Top bar */}
      <header className="flex items-center gap-4 px-4 py-3 border-b border-brand-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-brand-accent" />
          <span className="font-display font-bold text-sm">BrandForge</span>
        </div>
        <div className="flex-1">
          <BrandCoherenceScore />
        </div>
        <span className="text-xs text-brand-muted font-mono">
          {campaignId?.slice(0, 8)}
        </span>
      </header>

      {/* Main canvas area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Agent Pipeline */}
        <div className="w-56 flex-shrink-0 border-r border-brand-border overflow-y-auto hidden md:block">
          <AgentPipeline />
        </div>

        {/* Center: Generative Feed */}
        <div className="flex-1 flex flex-col min-w-0">
          {isComplete ? <CampaignComplete /> : <GenerativeFeed />}
        </div>

        {/* Right: Brand DNA Viewer */}
        <div className="w-64 flex-shrink-0 border-l border-brand-border overflow-y-auto hidden lg:block">
          <BrandDNAViewer />
        </div>
      </div>

      {/* Mobile: Bottom tabs for panels */}
      <nav className="md:hidden flex border-t border-brand-border" aria-label="Mobile panel navigation">
        <MobileTab label="Pipeline" panel="pipeline" />
        <MobileTab label="Feed" panel="feed" active />
        <MobileTab label="Brand DNA" panel="dna" />
      </nav>
    </div>
  );
}

function MobileTab({ label, active }) {
  return (
    <button
      className={`flex-1 py-3 text-xs font-medium text-center transition-colors
        ${active ? "text-brand-accent border-t-2 border-brand-accent" : "text-brand-muted"}`}
      aria-label={label}
    >
      {label}
    </button>
  );
}
