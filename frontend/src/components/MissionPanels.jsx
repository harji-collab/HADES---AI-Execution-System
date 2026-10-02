import { Check, Circle, ShieldAlert, X } from "lucide-react";

const FLOW = [
  "PLANNING",
  "READY",
  "APPROVAL",
  "EXECUTING",
  "VERIFYING",
  "RECOVERY REQUIRED",
  "HUMAN APPROVAL",
  "RE-EXECUTION",
  "RE-VERIFYING",
  "VERIFIED RESULT",
];

export function MissionProgress({ phase = "PLANNING", recoveryUsed = false }) {
  const finalBlocked = phase === "BLOCKED";
  const phaseIndex = FLOW.indexOf(phase);
  return (
    <section className="mission-flow-card" aria-label="Mission lifecycle">
      <div className="mission-flow-heading">
        <div>
          <span className="flow-eyebrow">HADES EXECUTION LOOP</span>
          <h2>{finalBlocked ? "MISSION BLOCKED" : phase}</h2>
        </div>
        <span className={`flow-state-pill ${finalBlocked ? "flow-state-blocked" : ""}`}>{finalBlocked ? "BLOCKED" : phase}</span>
      </div>
      <ol className="mission-flow-list">
        {FLOW.map((step, index) => {
          const skippedRecovery = !recoveryUsed && !finalBlocked && index >= 5 && index < 9 && phase === "VERIFIED RESULT";
          const complete = !finalBlocked && phaseIndex > index;
          const active = phase === step;
          return (
            <li key={step} className={`mission-flow-step ${complete ? "is-complete" : ""} ${active ? "is-active" : ""} ${skippedRecovery ? "is-optional" : ""}`}>
              <span className="flow-step-icon">
                {complete ? <Check size={12} /> : finalBlocked && step === "VERIFIED RESULT" ? <X size={12} /> : <Circle size={8} />}
              </span>
              <span>{step}</span>
            </li>
          );
        })}
      </ol>
      {(finalBlocked || phase === "INTERRUPTED") && <div className="flow-blocked-note"><ShieldAlert size={14} /> {phase === "INTERRUPTED" ? "The connection ended before a final result. Review the mission status and retry with a new mission." : "Requirements remain unmet. Review the evidence and recovery record."}</div>}
    </section>
  );
}

export function VerificationPanel({ verification }) {
  if (!verification) return null;
  return (
    <section className={`mission-panel verification-panel ${verification.passed ? "verification-pass" : "verification-fail"}`}>
      <div className="mission-panel-header">
        <div><span className="flow-eyebrow">REQUIREMENT-DRIVEN CHECK</span><h3>Verification</h3></div>
        <span className="verification-score">{Math.round((verification.score || 0) * 100)}%</span>
      </div>
      <p className="panel-status-line">{verification.passed ? "All requirements passed against recorded evidence." : "One or more requirements are missing or failed."}</p>
      <ul className="requirement-result-list">
        {(verification.requirement_results || []).map((item, index) => (
          <li key={`${item.requirement}-${index}`} className="requirement-result-row">
            <span className={`requirement-state requirement-${item.status}`}>{item.status === "satisfied" ? "PASS" : item.status === "stale" ? "STALE" : "MISSING"}</span>
            <span className="requirement-copy"><strong>{item.requirement}</strong><small>{item.reason}</small></span>
            {(item.verifier || item.affected_task) && <span className="requirement-task" title={item.verifier ? `Judged by ${item.verifier}` : undefined}>{item.verifier || item.affected_task}</span>}
          </li>
        ))}
      </ul>
      {(verification.warnings || []).map((warning) => <p className="verification-warning" key={warning}>{warning}</p>)}
    </section>
  );
}

export function EvidencePanel({ evidence = [] }) {
  if (!evidence.length) return null;
  const successful = evidence.filter((item) => item.status === "complete").length;
  const failed = evidence.filter((item) => item.status === "failed" || item.status === "blocked").length;
  const stale = evidence.filter((item) => item.status === "stale").length;
  return (
    <details className="mission-panel evidence-panel" open>
      <summary className="mission-panel-header evidence-summary">
        <div><span className="flow-eyebrow">EXECUTION RECORD</span><h3>Evidence</h3></div>
        <span className="evidence-counts"><span>{successful} passed</span>{failed > 0 && <span className="text-rose-300">{failed} failed</span>}{stale > 0 && <span className="text-amber-300">{stale} stale</span>}</span>
      </summary>
      <div className="evidence-record-list">
        {evidence.map((item, index) => (
          <article className="evidence-record" key={`${item.step}-${item.started_at || index}-${index}`}>
            <div className="evidence-record-heading">
              <div className="min-w-0"><strong>{item.step || item.tool}</strong><span>{item.tool}{item.recovery ? " · recovery run" : ""}</span></div>
              <span className={`evidence-status evidence-${item.status}`}>{item.status}</span>
            </div>
            <p className="evidence-meta">Risk: {item.risk || "—"} · Permissions: {(item.permissions || []).join(", ") || "—"}{item.provider ? ` · ${item.provider}` : ""}</p>
            {item.inputs && <details className="evidence-inputs"><summary>Inputs and evidence links</summary><pre>{JSON.stringify(item.inputs, null, 2)}</pre></details>}
            {(item.output || item.error) && <pre className="evidence-output">{item.output || item.error}</pre>}
          </article>
        ))}
      </div>
    </details>
  );
}
