import { motion } from "framer-motion";
import { ShieldCheck } from "lucide-react";
import useCampaignStore from "../../stores/campaignStore";
import ProgressBar from "../shared/ProgressBar";

export default function BrandCoherenceScore() {
  const score = useCampaignStore((s) => s.brandCoherenceScore);

  return (
    <div className="glass-panel px-4 py-3 flex items-center gap-4">
      <ShieldCheck size={20} className="text-brand-accent flex-shrink-0" />
      <div className="flex-1">
        <ProgressBar value={score} label="Brand Coherence" />
      </div>
      <motion.span
        key={Math.round(score)}
        initial={{ scale: 1.3, color: "#7C5CFC" }}
        animate={{ scale: 1, color: "#ffffff" }}
        className="text-lg font-bold tabular-nums w-14 text-right"
      >
        {Math.round(score)}%
      </motion.span>
    </div>
  );
}
