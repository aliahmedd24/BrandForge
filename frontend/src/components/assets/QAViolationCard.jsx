import { motion } from "framer-motion";
import { AlertTriangle, RefreshCw } from "lucide-react";

const violationVariants = {
  hidden: { opacity: 0, x: 20, borderColor: "transparent" },
  visible: {
    opacity: 1,
    x: 0,
    borderColor: "#EF4444",
    transition: { duration: 0.3, type: "spring", stiffness: 300 },
  },
};

export default function QAViolationCard({ result }) {
  if (!result) return null;

  const score = Math.round((result.overall_score || 0) * 100);

  return (
    <motion.div
      variants={violationVariants}
      initial="hidden"
      animate="visible"
      className="border-2 border-brand-danger rounded-xl p-4 bg-brand-danger/5 space-y-3"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle
          size={18}
          className="text-brand-danger flex-shrink-0 mt-0.5"
        />
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-brand-danger">
              Brand Alignment: {score}%
            </h4>
            <span className="text-[10px] uppercase text-brand-danger font-bold">
              {result.status}
            </span>
          </div>
          <p className="text-xs text-brand-muted mt-1">
            Asset: {result.asset_id} ({result.asset_type})
          </p>
        </div>
      </div>

      {result.violations?.length > 0 && (
        <div className="space-y-2 pl-7">
          {result.violations.slice(0, 3).map((v, i) => (
            <div key={i} className="text-xs space-y-0.5">
              <p className="text-white">
                <span
                  className={`inline-block px-1.5 py-0.5 rounded text-[9px] uppercase font-bold mr-1.5
                    ${
                      v.severity === "critical"
                        ? "bg-brand-danger/20 text-brand-danger"
                        : v.severity === "moderate"
                          ? "bg-brand-warning/20 text-brand-warning"
                          : "bg-brand-muted/20 text-brand-muted"
                    }`}
                >
                  {v.severity}
                </span>
                {v.description}
              </p>
              <p className="text-brand-muted">
                Expected: {v.expected} | Found: {v.found}
              </p>
            </div>
          ))}
        </div>
      )}

      {result.correction_prompt && (
        <div className="flex items-center gap-2 pl-7">
          <RefreshCw size={12} className="text-brand-accent animate-spin" />
          <span className="text-xs text-brand-accent">Regenerating...</span>
        </div>
      )}
    </motion.div>
  );
}
