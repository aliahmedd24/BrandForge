import { motion } from "framer-motion";
import { Maximize2 } from "lucide-react";
import { getSignedUrl } from "../../lib/storage";
import useCampaignStore from "../../stores/campaignStore";

function aspectClass(ratio) {
  switch (ratio) {
    case "9:16":
      return "aspect-[9/16]";
    case "16:9":
      return "aspect-video";
    default:
      return "aspect-square";
  }
}

const imageVariants = {
  hidden: { opacity: 0, filter: "blur(12px)", scale: 1.03 },
  visible: {
    opacity: 1,
    filter: "blur(0px)",
    scale: 1,
    transition: { duration: 0.6 },
  },
};

export default function ImageAssetCard({ image, variantLabel, compact }) {
  const qaResults = useCampaignStore((s) => s.qaResults);
  const setActive = useCampaignStore((s) => s.setActiveAsset);
  const qa = qaResults[image.id];

  const url = getSignedUrl(image.gcs_url);
  const failed = qa?.status === "failed";

  return (
    <motion.div
      variants={imageVariants}
      initial="hidden"
      animate="visible"
      className={`relative group rounded-xl overflow-hidden border-2 transition-colors
        ${failed ? "border-brand-danger" : "border-brand-border hover:border-brand-accent/40"}`}
    >
      <img
        src={url}
        alt={`Generated ${image.platform} ${image.spec?.use_case || "image"}`}
        className={`w-full ${compact ? "aspect-[4/5]" : aspectClass(image.spec?.aspect_ratio)} object-cover`}
        loading="lazy"
      />

      {/* QA badge */}
      {qa && (
        <div
          className={`absolute top-2 right-2 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase
            ${
              qa.status === "approved"
                ? "bg-brand-success/90 text-white"
                : qa.status === "failed"
                  ? "bg-brand-danger/90 text-white"
                  : "bg-brand-warning/90 text-black"
            }`}
        >
          {qa.status === "approved"
            ? `${Math.round(qa.overall_score * 100)}%`
            : qa.status}
        </div>
      )}

      {/* Hover overlay */}
      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
        <button
          onClick={() => setActive(image.id)}
          aria-label="View full size"
          className="p-3 bg-white/10 backdrop-blur rounded-full hover:bg-white/20 transition-colors"
        >
          <Maximize2 size={18} />
        </button>
      </div>

      {/* Platform label */}
      <div className="absolute bottom-2 left-2 px-2 py-0.5 bg-black/60 backdrop-blur rounded text-[10px] font-medium uppercase">
        {image.platform}
      </div>

      {/* Regeneration shimmer */}
      {failed && (
        <div className="absolute inset-0 bg-gradient-to-r from-brand-danger/0 via-brand-danger/20 to-brand-danger/0 animate-shimmer pointer-events-none" />
      )}
    </motion.div>
  );
}
