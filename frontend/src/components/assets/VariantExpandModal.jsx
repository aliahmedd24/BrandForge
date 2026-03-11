import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { getSignedUrl } from "../../lib/storage";
import useCampaignStore from "../../stores/campaignStore";

export default function VariantExpandModal({ image, onClose }) {
  const qaResults = useCampaignStore((s) => s.qaResults);
  if (!image) return null;

  const qa = qaResults[image.id];
  const url = getSignedUrl(image.gcs_url);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          className="glass-panel max-w-3xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-4"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between">
            <h3 className="font-display font-bold text-lg">
              {image.platform} — {image.spec?.use_case || "image"}
            </h3>
            <button onClick={onClose} className="p-1 hover:bg-white/10 rounded">
              <X size={18} />
            </button>
          </div>

          <img
            src={url}
            alt={`${image.platform} variant`}
            className="w-full rounded-lg"
          />

          <div className="space-y-2 text-sm">
            <div>
              <span className="text-brand-muted">Generation Prompt:</span>
              <p className="text-brand-muted/80 mt-1 text-xs font-mono bg-black/30 p-3 rounded-lg">
                {image.generation_prompt}
              </p>
            </div>

            {qa && (
              <div className="grid grid-cols-2 gap-3 mt-3">
                <div className="bg-black/20 p-3 rounded-lg">
                  <span className="text-brand-muted text-xs">Overall</span>
                  <p className="font-bold text-lg">{Math.round(qa.overall_score * 100)}%</p>
                </div>
                <div className="bg-black/20 p-3 rounded-lg">
                  <span className="text-brand-muted text-xs">Color Compliance</span>
                  <p className="font-bold text-lg">{Math.round(qa.color_compliance * 100)}%</p>
                </div>
                <div className="bg-black/20 p-3 rounded-lg">
                  <span className="text-brand-muted text-xs">Tone</span>
                  <p className="font-bold text-lg">{Math.round(qa.tone_compliance * 100)}%</p>
                </div>
                <div className="bg-black/20 p-3 rounded-lg">
                  <span className="text-brand-muted text-xs">Visual Energy</span>
                  <p className="font-bold text-lg">{Math.round(qa.visual_energy_compliance * 100)}%</p>
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
