import { motion } from "framer-motion";
import { getSignedUrl } from "../../lib/storage";

const imageVariants = {
  hidden: { opacity: 0, filter: "blur(12px)", scale: 1.03 },
  visible: (i) => ({
    opacity: 1,
    filter: "blur(0px)",
    scale: 1,
    transition: { duration: 0.6, delay: i * 0.15 },
  }),
};

export default function MoodBoardGrid({ images }) {
  if (!images?.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-2"
    >
      <h3 className="text-xs font-semibold text-brand-muted uppercase tracking-wider">
        Mood Board
      </h3>
      <div className="grid grid-cols-3 gap-2">
        {images.slice(0, 6).map((url, i) => (
          <motion.div
            key={url}
            custom={i}
            variants={imageVariants}
            initial="hidden"
            animate="visible"
            className="aspect-square rounded-lg overflow-hidden border border-brand-border"
          >
            <img
              src={getSignedUrl(url)}
              alt={`Mood board reference ${i + 1}`}
              className="w-full h-full object-cover"
              loading="lazy"
            />
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
