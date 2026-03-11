import { motion, AnimatePresence } from "framer-motion";
import useCampaignStore from "../../stores/campaignStore";
import ColorSwatch from "../shared/ColorSwatch";

export default function BrandDNAViewer() {
  const dna = useCampaignStore((s) => s.brandDNA);

  if (!dna) {
    return (
      <aside className="glass-panel p-4" aria-label="Brand DNA viewer">
        <h2 className="text-xs font-semibold text-brand-muted uppercase tracking-wider mb-3">
          Brand DNA
        </h2>
        <p className="text-sm text-brand-muted italic">
          Waiting for Brand Strategist...
        </p>
      </aside>
    );
  }

  const palette = dna.color_palette;

  return (
    <aside className="glass-panel p-4 space-y-4 overflow-y-auto" aria-label="Brand DNA viewer">
      <h2 className="text-xs font-semibold text-brand-muted uppercase tracking-wider">
        Brand DNA
      </h2>

      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Brand Essence */}
          <div>
            <h3 className="text-[11px] text-brand-muted uppercase tracking-wider mb-1">
              Essence
            </h3>
            <p className="text-sm font-medium">{dna.brand_essence}</p>
          </div>

          {/* Personality */}
          <div>
            <h3 className="text-[11px] text-brand-muted uppercase tracking-wider mb-1.5">
              Personality
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {dna.brand_personality?.map((trait) => (
                <span
                  key={trait}
                  className="px-2 py-0.5 text-xs bg-brand-accent/15 text-brand-accent rounded-full"
                >
                  {trait}
                </span>
              ))}
            </div>
          </div>

          {/* Color Palette */}
          {palette && (
            <div>
              <h3 className="text-[11px] text-brand-muted uppercase tracking-wider mb-2">
                Palette
              </h3>
              <div className="flex gap-2 flex-wrap">
                <ColorSwatch color={palette.primary} label="Primary" size="sm" />
                <ColorSwatch color={palette.secondary} label="Secondary" size="sm" />
                <ColorSwatch color={palette.accent} label="Accent" size="sm" />
                <ColorSwatch color={palette.background} label="BG" size="sm" />
                <ColorSwatch color={palette.text} label="Text" size="sm" />
              </div>
            </div>
          )}

          {/* Typography */}
          {dna.typography && (
            <div>
              <h3 className="text-[11px] text-brand-muted uppercase tracking-wider mb-1">
                Typography
              </h3>
              <p className="text-xs text-brand-muted">
                {dna.typography.heading_font} / {dna.typography.body_font}
              </p>
            </div>
          )}

          {/* Tone */}
          <div>
            <h3 className="text-[11px] text-brand-muted uppercase tracking-wider mb-1">
              Tone
            </h3>
            <p className="text-xs text-brand-muted line-clamp-3">
              {dna.tone_of_voice}
            </p>
          </div>

          {/* Visual Direction */}
          <div>
            <h3 className="text-[11px] text-brand-muted uppercase tracking-wider mb-1">
              Visual Direction
            </h3>
            <p className="text-xs text-brand-muted line-clamp-3">
              {dna.visual_direction}
            </p>
          </div>
        </motion.div>
      </AnimatePresence>
    </aside>
  );
}
