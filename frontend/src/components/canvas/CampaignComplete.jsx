import { motion } from "framer-motion";
import { PartyPopper, Download, Send } from "lucide-react";
import useCampaignStore from "../../stores/campaignStore";
import { downloadBundle } from "../../lib/api";

export default function CampaignComplete() {
  const campaignId = useCampaignStore((s) => s.campaignId);
  const score = useCampaignStore((s) => s.brandCoherenceScore);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="glass-panel p-8 text-center space-y-6"
    >
      <motion.div
        initial={{ rotate: -10, scale: 0 }}
        animate={{ rotate: 0, scale: 1 }}
        transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
      >
        <PartyPopper size={48} className="mx-auto text-brand-accent" />
      </motion.div>

      <div>
        <h2 className="text-2xl font-display font-bold mb-2">
          Campaign Complete
        </h2>
        <p className="text-brand-muted">
          All assets generated and QA reviewed.
        </p>
      </div>

      {/* Animated score counter */}
      <div className="py-4">
        <p className="text-xs text-brand-muted uppercase tracking-wider mb-1">
          Brand Coherence Score
        </p>
        <motion.p
          className="text-5xl font-display font-bold text-brand-accent"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
        >
          {Math.round(score)}%
        </motion.p>
      </div>

      <div className="flex gap-3 justify-center">
        <button
          onClick={() => downloadBundle(campaignId)}
          className="flex items-center gap-2 px-5 py-3 bg-brand-accent hover:bg-brand-accent-hover rounded-xl font-semibold transition-colors"
        >
          <Download size={18} />
          Download Bundle
        </button>
        <button
          className="flex items-center gap-2 px-5 py-3 bg-brand-surface border border-brand-border hover:border-brand-accent/50 rounded-xl font-semibold transition-colors"
          aria-label="Post campaign (coming in Phase 5)"
        >
          <Send size={18} />
          Post Campaign
        </button>
      </div>
    </motion.div>
  );
}
