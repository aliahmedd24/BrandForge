import { motion } from "framer-motion";

export default function ProgressBar({ value, max = 100, label, showLabel = true }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color =
    pct >= 80
      ? "bg-brand-success"
      : pct >= 60
        ? "bg-brand-warning"
        : "bg-brand-danger";

  return (
    <div className="w-full" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label || "Progress"}>
      {showLabel && (
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-xs text-brand-muted font-medium">
            {label}
          </span>
          <span className="text-xs font-semibold text-white tabular-nums">
            {Math.round(pct)}%
          </span>
        </div>
      )}
      <div className="h-2 bg-brand-border rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
