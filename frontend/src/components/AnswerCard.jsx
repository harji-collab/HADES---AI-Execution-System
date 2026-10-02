import { ArrowDown, CheckCircle2, Cpu, Download, ShieldAlert, ShieldCheck, Hourglass } from "lucide-react";
import FinalSolution from "./FinalSolution";

// The one card a non-technical reader needs: what HADES is doing or what it
// produced, right under their question. Evidence lives further down the page.
function statusOf({ loading, phase, approvalRequired, recovery, verification, finalSolution }) {
  if (loading) return { tone: "working", label: phase === "PLANNING" ? "PLANNING" : "WORKING ON IT", Icon: Cpu };
  if (recovery?.kind === "amendment" && recovery?.status === "approval_required") return { tone: "decision", label: "NEEDS YOUR DECISION", Icon: Hourglass };
  if (approvalRequired) return { tone: "decision", label: "READY · NEEDS YOUR APPROVAL", Icon: ShieldCheck };
  if (recovery?.status === "approval_required") return { tone: "decision", label: "NEEDS YOUR APPROVAL", Icon: Hourglass };
  if (phase === "BLOCKED" || phase === "INTERRUPTED") return { tone: "blocked", label: phase === "BLOCKED" ? "COULD NOT COMPLETE" : "INTERRUPTED", Icon: ShieldAlert };
  if (verification?.passed && finalSolution) return { tone: "done", label: "DONE · VERIFIED", Icon: CheckCircle2 };
  return { tone: "working", label: phase || "WORKING", Icon: Cpu };
}

export default function AnswerCard({
  loading,
  phase,
  plan,
  approvalRequired,
  finalSolution,
  solutionMode,
  verification,
  recovery,
  result,
  lastActivity,
  onShowEvidence,
  onDownloadReceipt,
  receiptBusy,
}) {
  const status = statusOf({ loading, phase, approvalRequired, recovery, verification, finalSolution });
  const results = verification?.requirement_results || [];
  const satisfied = results.filter((item) => item.status === "satisfied").length;
  const unmet = results.filter((item) => item.status !== "satisfied");
  const requirements = plan?.contract?.requirements || [];

  return (
    <div className={`answer-card answer-${status.tone}`}>
      <div className="answer-status">
        <status.Icon size={14} className={status.tone === "working" ? "animate-spin" : ""} />
        <span>{status.label}</span>
        {results.length > 0 && !loading && <em>{satisfied}/{results.length} checks passed</em>}
      </div>

      {loading && finalSolution && (
        <p className="answer-note">Updating your answer… {lastActivity}</p>
      )}

      {finalSolution ? (
        <FinalSolution solution={finalSolution} mode={solutionMode} verification={verification} isComplete={!loading && Boolean(verification?.passed)} />
      ) : loading ? (
        <p className="answer-text">{lastActivity || (phase === "PLANNING" ? "Breaking your goal into checkable steps…" : "Running the plan…")}</p>
      ) : approvalRequired && plan ? (
        <div className="answer-text">
          <p>Here is what I will do. Nothing runs until you approve.</p>
          <ul className="answer-list">
            {requirements.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : (
        <div className="answer-text">
          <p>{result || "No answer yet."}</p>
          {unmet.length > 0 && (
            <ul className="answer-list answer-list-unmet">
              {unmet.map((item) => <li key={item.requirement_id || item.requirement}><strong>{item.requirement}</strong> — {item.reason}</li>)}
            </ul>
          )}
        </div>
      )}

      {finalSolution && !loading && result && status.tone !== "done" && <p className="answer-note answer-note-warn">{result}</p>}

      {(plan || finalSolution) && (
        <div className="answer-actions">
          <button type="button" onClick={onShowEvidence}><ArrowDown size={13} /> See evidence &amp; verification</button>
          {onDownloadReceipt && verification && (
            <button type="button" onClick={onDownloadReceipt} disabled={receiptBusy}><Download size={13} /> {receiptBusy ? "Preparing…" : "Download receipt"}</button>
          )}
        </div>
      )}
    </div>
  );
}
