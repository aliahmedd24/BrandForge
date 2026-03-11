import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import useCampaignStore from "../../stores/campaignStore";
import ImageAssetCard from "../assets/ImageAssetCard";
import VariantShowcase from "../assets/VariantShowcase";
import VideoAssetCard from "../assets/VideoAssetCard";
import CopyAssetCard from "../assets/CopyAssetCard";
import MoodBoardGrid from "../assets/MoodBoardGrid";
import QAViolationCard from "../assets/QAViolationCard";
import ColorSwatch from "../shared/ColorSwatch";
import StreamingText from "../shared/StreamingText";

const feedItemVariants = {
  hidden: { opacity: 0, y: 24, scale: 0.97 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] },
  },
  exit: { opacity: 0, scale: 0.95, transition: { duration: 0.2 } },
};

function BrandDNACard({ dna }) {
  const palette = dna.color_palette;
  return (
    <div className="glass-panel p-5 space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-brand-accent" />
        <span className="text-[11px] uppercase tracking-wider text-brand-accent font-semibold">
          Brand Strategist
        </span>
      </div>

      <div>
        <h3 className="text-lg font-display font-bold mb-1">
          {dna.brand_name}
        </h3>
        <p className="text-sm text-brand-muted">
          <StreamingText text={dna.brand_essence} speed={25} />
        </p>
      </div>

      {palette && (
        <div className="flex gap-3 flex-wrap">
          <ColorSwatch color={palette.primary} label="Primary" />
          <ColorSwatch color={palette.secondary} label="Secondary" />
          <ColorSwatch color={palette.accent} label="Accent" />
          <ColorSwatch color={palette.background} label="BG" />
          <ColorSwatch color={palette.text} label="Text" />
        </div>
      )}

      {dna.brand_personality && (
        <div className="flex flex-wrap gap-1.5">
          {dna.brand_personality.map((t) => (
            <span
              key={t}
              className="px-2.5 py-1 text-xs bg-brand-accent/10 text-brand-accent rounded-full"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function FeedItem({ item }) {
  switch (item.type) {
    case "brand_dna":
      return <BrandDNACard dna={item.payload} />;
    case "mood_board":
      return <MoodBoardGrid images={item.payload} />;
    case "image":
      return <ImageAssetCard image={item.payload} />;
    case "variant_group":
      return <VariantShowcase variants={item.payload.variants} specKey={item.payload.specKey} />;
    case "video":
      return <VideoAssetCard video={item.payload} />;
    case "copy":
      return <CopyAssetCard copy={item.payload} streaming />;
    case "qa_violation":
      return <QAViolationCard result={item.payload} />;
    case "script":
      return (
        <div className="glass-panel p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-1.5 rounded-full bg-brand-accent" />
            <span className="text-[11px] uppercase tracking-wider text-brand-accent font-semibold">
              Scriptwriter
            </span>
          </div>
          <p className="text-sm text-brand-muted">
            <StreamingText text={item.payload?.hook || ""} speed={30} />
          </p>
        </div>
      );
    default:
      return null;
  }
}

export default function GenerativeFeed() {
  const feedItems = useCampaignStore((s) => s.feedItems);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [feedItems.length]);

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto feed-scroll space-y-4 p-4"
      role="feed"
      aria-label="Campaign generation feed"
    >
      <AnimatePresence mode="popLayout">
        {feedItems.map((item) => (
          <motion.div
            key={item.id}
            variants={feedItemVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            layout
          >
            <FeedItem item={item} />
          </motion.div>
        ))}
      </AnimatePresence>

      {feedItems.length === 0 && (
        <div className="flex items-center justify-center h-full">
          <p className="text-brand-muted text-sm italic">
            Agents are starting up...
          </p>
        </div>
      )}
    </div>
  );
}
