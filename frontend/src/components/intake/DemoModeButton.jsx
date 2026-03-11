import { Play } from "lucide-react";
import { motion } from "framer-motion";

export default function DemoModeButton({ onClick, loading }) {
  return (
    <motion.button
      onClick={onClick}
      disabled={loading}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className={`w-full max-w-md mx-auto flex items-center justify-center gap-3 py-4 px-6
        bg-gradient-to-r from-brand-accent to-emerald-500 rounded-2xl
        font-display font-bold text-lg text-white
        shadow-lg shadow-brand-accent/25
        hover:shadow-xl hover:shadow-brand-accent/40
        disabled:opacity-50 disabled:cursor-not-allowed
        transition-shadow duration-300`}
    >
      <Play size={22} fill="currentColor" />
      {loading ? "Launching Demo..." : "Launch Demo \u2014 \"Grounded\" Sneakers"}
    </motion.button>
  );
}
