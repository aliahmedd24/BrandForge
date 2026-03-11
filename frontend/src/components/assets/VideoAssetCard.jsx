import { useState } from "react";
import { motion } from "framer-motion";
import { Play, Pause } from "lucide-react";
import { getSignedUrl } from "../../lib/storage";
import LoadingShimmer from "../shared/LoadingShimmer";

export default function VideoAssetCard({ video }) {
  const [playing, setPlaying] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const url = getSignedUrl(video.gcs_url_final);
  const isGenerating = video.generation_status === "processing";

  if (isGenerating) {
    return (
      <div className="rounded-xl overflow-hidden">
        <LoadingShimmer height="h-48" />
        <div className="p-3 bg-brand-surface">
          <p className="text-xs text-brand-muted animate-pulse">
            Generating video for {video.platform}...
          </p>
        </div>
      </div>
    );
  }

  const togglePlay = () => {
    const el = document.getElementById(`video-${video.id}`);
    if (!el) return;
    if (playing) {
      el.pause();
    } else {
      el.play();
    }
    setPlaying(!playing);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="rounded-xl overflow-hidden border border-brand-border"
    >
      <div className="relative bg-black aspect-video">
        <video
          id={`video-${video.id}`}
          src={url}
          className="w-full h-full object-contain"
          onLoadedData={() => setLoaded(true)}
          onEnded={() => setPlaying(false)}
          playsInline
          aria-label={`Campaign video for ${video.platform}`}
        />
        <button
          onClick={togglePlay}
          aria-label={playing ? "Pause video" : "Play video"}
          className="absolute inset-0 flex items-center justify-center bg-black/30 hover:bg-black/20 transition-colors"
        >
          {!playing && loaded && (
            <div className="p-3 bg-white/10 backdrop-blur rounded-full">
              <Play size={24} fill="white" />
            </div>
          )}
          {playing && (
            <div className="p-3 bg-white/10 backdrop-blur rounded-full opacity-0 hover:opacity-100 transition-opacity">
              <Pause size={24} fill="white" />
            </div>
          )}
        </button>
      </div>
      <div className="p-3 bg-brand-surface flex items-center justify-between">
        <span className="text-xs font-medium uppercase text-brand-muted">
          {video.platform} &middot; {video.duration_seconds}s
        </span>
        <span className="text-xs text-brand-muted">
          {video.aspect_ratio}
        </span>
      </div>
    </motion.div>
  );
}
