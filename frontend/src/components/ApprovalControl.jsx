import { motion } from "framer-motion";
import { Check, ShieldCheck, Cpu, X } from "lucide-react";

export default function ApprovalControl({
  onApprove,
  onReset,
  isLocal = true,
  loading = false,
  title = "PLAN READY",
  approveLabel = "Approve & Run",
  cancelLabel = "Cancel",
  description,
}) {
  const subtitle = description || (isLocal
    ? "Human approval is required before local execution"
    : "External interaction requires human authorization");

  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="sticky-approval-dock"
    >
      <div className="dock-content">
        <div className="dock-left flex items-center gap-3">
          <div className="dock-shield-icon">
            <ShieldCheck size={18} className="text-cyan-400" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold text-white tracking-wide">
                {title}
              </span>
              <span className="dock-badge-pulse" />
            </div>
            <span className="text-[11px] text-white/50 hidden sm:inline">
              {subtitle}
            </span>
          </div>
        </div>

        <div className="dock-right flex items-center gap-2">
          <button
            onClick={onReset}
            disabled={loading}
            className="dock-cancel-btn"
            title={cancelLabel}
          >
            <X size={14} />
            <span className="hidden sm:inline">{cancelLabel}</span>
          </button>

          <button
            onClick={onApprove}
            disabled={loading}
            className="dock-approve-btn"
          >
            {loading ? (
              <>
                <Cpu size={15} className="animate-spin" />
                <span>RUNNING...</span>
              </>
            ) : (
              <>
                <Check size={15} />
                <span>{approveLabel}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
