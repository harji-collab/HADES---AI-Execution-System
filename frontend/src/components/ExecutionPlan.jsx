import { motion } from "framer-motion";
import { Sparkles, Check, ShieldCheck, Cpu } from "lucide-react";

function toolLabel(tool) {
  const labels = {
    planning: "Planning",
    research: "Research",
    content: "Content",
    verification: "Verification",
  };
  return labels[tool] || tool || "Tool";
}

export default function ExecutionPlan({
  plan,
  isLocal = true,
  approvalRequired = false,
  onApprove,
  loading = false,
}) {
  if (!plan) return null;
  const riskLevel = plan.approval?.risk || (isLocal ? "LOW" : "HIGH");

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="execution-plan-card"
    >
      {/* CARD HEADER */}
      <div className="plan-card-header">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-cyan-400" />
          <span className="font-mono text-[11px] font-semibold tracking-wider text-cyan-300 uppercase">
            MISSION CONTRACT
          </span>
        </div>
        <div className="plan-badge-ready font-mono text-[10px]">
          READY FOR EXECUTION
        </div>
      </div>

      {/* SUMMARY */}
      <section className="contract-section">
        <div className="contract-section-label">GOAL</div>
        <p className="contract-objective">{plan.contract?.objective || plan.goal}</p>
      </section>

      {plan.contract?.requirements?.length > 0 && (
        <section className="contract-section">
          <div className="contract-section-label">REQUIREMENTS</div>
          <ul className="contract-requirements">
            {plan.contract.requirements.map((requirement, index) => <li key={`${index}-${requirement}`}>{requirement}</li>)}
          </ul>
        </section>
      )}

      {plan.summary && (
        <p className="plan-summary-text">{plan.summary}</p>
      )}

      {/* STEPS LIST */}
      <div className="contract-section-label tool-router-label">TOOL ROUTER · TASK DEPENDENCIES</div>
      <div className="plan-steps-list">
        {plan.steps?.map((step, index) => {
          const stepNumber = String(index + 1).padStart(2, "0");
          return (
            <div key={step.id || index} className="plan-step-item">
              <span className="step-num font-mono text-cyan-400/90">{stepNumber}</span>
              <span className="step-task text-white/90">
                {step.task || step.title}
              </span>
              <span className="step-tool-stack"><span className="step-tool-badge font-mono">{toolLabel(step.tool)}</span>{step.depends_on?.length > 0 && <small>after {step.depends_on.join(", ")}</small>}</span>
            </div>
          );
        })}
      </div>

      {/* FOOTER & APPROVAL ACTION */}
      <div className="plan-card-footer">
        <div className="plan-risk-indicator">
          <ShieldCheck size={14} className={isLocal ? "text-emerald-400" : "text-amber-400"} />
          <div className="flex flex-col">
            <span className="font-mono text-[11px] text-white/80 font-medium">
              {riskLevel === "HIGH" ? "High-impact mission" : isLocal ? "Local execution" : "External interaction"}
            </span>
            <span className="text-[10px] text-white/40">
              {plan.approval?.reason || (riskLevel === "HIGH" ? "Requires explicit human authorization" : "Human approval is required before execution")}
            </span>
          </div>
        </div>

        {approvalRequired && (
          <button
            onClick={onApprove}
            disabled={loading}
            className="approve-plan-btn"
          >
            {loading ? (
              <span className="flex items-center gap-2 font-mono">
                <Cpu size={15} className="animate-spin" />
                EXECUTING...
              </span>
            ) : (
              <span className="flex items-center gap-2 font-mono font-semibold">
                <Check size={15} />
                APPROVE & RUN
              </span>
            )}
          </button>
        )}
      </div>
    </motion.div>
  );
}
