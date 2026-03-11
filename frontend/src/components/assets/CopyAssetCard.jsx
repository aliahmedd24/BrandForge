import { motion } from "framer-motion";
import { Copy, Hash } from "lucide-react";
import StreamingText from "../shared/StreamingText";

export default function CopyAssetCard({ copy, streaming = false }) {
  if (!copy) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="glass-panel p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase text-brand-accent tracking-wider">
          {copy.platform}
        </span>
        {copy.brand_voice_score != null && (
          <span className="text-[10px] text-brand-muted">
            Voice: {Math.round(copy.brand_voice_score * 100)}%
          </span>
        )}
      </div>

      <h4 className="text-sm font-semibold">{copy.headline}</h4>

      <p className="text-sm text-brand-muted leading-relaxed">
        {streaming ? (
          <StreamingText text={copy.caption} speed={15} />
        ) : (
          copy.caption
        )}
      </p>

      {copy.hashtags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {copy.hashtags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-0.5 px-2 py-0.5 text-xs bg-brand-accent/10 text-brand-accent rounded-full"
            >
              <Hash size={10} />
              {tag.replace("#", "")}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-2 border-t border-brand-border">
        <span className="text-[10px] text-brand-muted">
          CTA: {copy.cta_text}
        </span>
        <span className="text-[10px] text-brand-muted">
          {copy.character_count} chars
        </span>
      </div>
    </motion.div>
  );
}
