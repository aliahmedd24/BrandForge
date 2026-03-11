import { Pin } from "lucide-react";
import { motion } from "framer-motion";
import ImageAssetCard from "./ImageAssetCard";
import useCampaignStore from "../../stores/campaignStore";

function ScoreBadge({ score }) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.85
      ? "bg-brand-success/90"
      : score >= 0.8
        ? "bg-brand-warning/90 text-black"
        : "bg-brand-danger/90";

  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${color}`}>
      {pct}%
    </span>
  );
}

export default function VariantShowcase({ variants, specKey }) {
  const qaResults = useCampaignStore((s) => s.qaResults);
  const pinnedVariants = useCampaignStore((s) => s.pinnedVariants);
  const setPinnedVariant = useCampaignStore((s) => s.setPinnedVariant);

  const pinned = pinnedVariants[specKey];
  const labels = ["A", "B", "C"];

  return (
    <div className="glass-panel p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-brand-accent" />
          <span className="text-[11px] uppercase tracking-wider text-brand-accent font-semibold">
            A/B Variants — {specKey.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {variants.map((img, i) => {
          const qa = qaResults[img.id];
          const isPinned = pinned === img.id;

          return (
            <motion.div
              key={img.id}
              className={`relative ${isPinned ? "ring-2 ring-brand-accent rounded-xl" : ""}`}
              whileHover={{ scale: 1.02 }}
            >
              <div className="absolute top-1 left-1 z-10 px-1.5 py-0.5 bg-black/70 backdrop-blur rounded text-[10px] font-bold">
                {labels[i]}
              </div>
              {qa && (
                <div className="absolute top-1 right-1 z-10">
                  <ScoreBadge score={qa.overall_score} />
                </div>
              )}
              <ImageAssetCard image={img} variantLabel={labels[i]} compact />
              <button
                onClick={() => setPinnedVariant(specKey, img.id)}
                className={`absolute bottom-1 right-1 z-10 p-1 rounded-full backdrop-blur transition-colors
                  ${isPinned ? "bg-brand-accent text-white" : "bg-black/50 text-white/70 hover:text-white"}`}
                aria-label={`Pin variant ${labels[i]}`}
              >
                <Pin size={12} />
              </button>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
