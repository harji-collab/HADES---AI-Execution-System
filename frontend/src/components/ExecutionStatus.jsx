import { motion } from "framer-motion";
import { Check, Cpu, AlertCircle } from "lucide-react";

export default function ExecutionStatus({ stages, isExecuting = true, phase = "" }) {
  if (!stages || !stages.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="execution-status-container"
    >
      <div className="status-header">
        <div className="flex items-center gap-2">
          <span className="status-pulsing-orb" />
          <span className="font-mono text-xs font-semibold tracking-wider text-cyan-300">
            {isExecuting ? `${phase || "EXECUTING"} · MISSION IN PROGRESS` : `${phase || "MISSION"} · EXECUTION PROGRESS`}
          </span>
        </div>
      </div>

      <div className="status-steps-list">
        {stages.map((stage) => {
          const complete = stage.status === "complete";
          const running = stage.status === "running";
          const error = stage.status === "error";

          return (
            <div
              key={stage.id}
              className={`status-step-row ${
                complete
                  ? "step-complete"
                  : running
                  ? "step-running"
                  : error
                  ? "step-error"
                  : "step-idle"
              }`}
            >
              <div className="step-icon-area">
                {complete ? (
                  <div className="icon-complete">
                    <Check size={12} className="text-emerald-400" />
                  </div>
                ) : running ? (
                  <div className="icon-running">
                    <Cpu size={12} className="text-cyan-400 animate-spin" />
                  </div>
                ) : error ? (
                  <div className="icon-error">
                    <AlertCircle size={12} className="text-rose-400" />
                  </div>
                ) : (
                  <div className="icon-idle">
                    <span className="w-1.5 h-1.5 rounded-full bg-white/20" />
                  </div>
                )}
              </div>

              <span className="step-label font-mono text-xs">
                {stage.title}
              </span>

              {running && (
                <span className="step-active-glow" />
              )}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
