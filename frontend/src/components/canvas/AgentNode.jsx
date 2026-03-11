import { motion } from "framer-motion";
import {
  Circle,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";

const STATUS_CONFIG = {
  idle: {
    Icon: Circle,
    color: "text-brand-muted",
    bg: "",
    label: "Waiting",
  },
  running: {
    Icon: Loader2,
    color: "text-brand-accent",
    bg: "bg-brand-accent/10",
    label: "Running",
    spin: true,
  },
  complete: {
    Icon: CheckCircle2,
    color: "text-brand-success",
    bg: "bg-brand-success/10",
    label: "Complete",
  },
  failed: {
    Icon: AlertCircle,
    color: "text-brand-danger",
    bg: "bg-brand-danger/10",
    label: "Failed",
  },
};

const AGENT_LABELS = {
  brand_strategist: "Brand Strategist",
  scriptwriter: "Scriptwriter",
  mood_board_director: "Mood Board",
  image_generator: "Image Generator",
  video_producer: "Video Producer",
  copy_editor: "Copy Editor",
  production_orchestrator: "Production Orchestrator",
  brand_qa_inspector: "QA Inspector",
  campaign_assembler: "Campaign Assembler",
  qa_orchestrator: "QA Pipeline",
  brandforge_root: "Orchestrator",
};

export default function AgentNode({ name, status, onRetry }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.idle;
  const { Icon, color, bg, label, spin } = config;

  return (
    <motion.div
      layout
      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${bg}`}
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
    >
      <Icon
        size={16}
        className={`${color} flex-shrink-0 ${spin ? "animate-spin" : ""}`}
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">
          {AGENT_LABELS[name] || name}
        </p>
        <p className={`text-xs ${color}`}>{label}</p>
      </div>
      {status === "failed" && onRetry && (
        <button
          onClick={() => onRetry(name)}
          aria-label={`Retry ${AGENT_LABELS[name] || name}`}
          className="p-1 text-brand-danger hover:text-white transition-colors"
        >
          <RefreshCw size={14} />
        </button>
      )}
    </motion.div>
  );
}
