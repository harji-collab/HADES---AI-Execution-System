import { FileDiff, ShieldAlert, X } from "lucide-react";

function formatValue(key, value) {
  if (value == null) return "—";
  if (key === "max_budget" && typeof value === "number") return `₹${value.toLocaleString("en-IN")}`;
  return String(value);
}

export default function AmendmentModal({ recovery, loading = false, onChoose, onReject, onClose }) {
  const failed = recovery?.requirement_results || [];
  return (
    <div className="amendment-overlay" role="dialog" aria-modal="true" aria-labelledby="amendment-title">
      <div className="amendment-card">
        <div className="amendment-header">
          <div>
            <span className="flow-eyebrow">HUMAN APPROVAL · CONTRACT CHANGE</span>
            <h2 id="amendment-title">Contract amendment required</h2>
          </div>
          <button type="button" className="amendment-close" onClick={onClose} title="Review first" aria-label="Review first">
            <X size={16} />
          </button>
        </div>

        <p className="amendment-reason">{recovery?.reason}</p>
        {failed.map((item) => (
          <p key={item.requirement_id || item.requirement} className="amendment-failure">
            <ShieldAlert size={13} /> <span><strong>{item.requirement}</strong> — {item.reason}</span>
          </p>
        ))}

        <div className="amendment-options">
          {(recovery?.options || []).map((option) => (
            <section key={option.id} className="amendment-option">
              <div className="amendment-option-title"><FileDiff size={14} /> {option.label}</div>
              <table className="amendment-diff">
                <tbody>
                  {Object.entries(option.diff || {}).map(([key, item]) => (
                    <tr key={key}>
                      <th>{key}</th>
                      <td className="diff-before">{formatValue(key, item.before)}</td>
                      <td aria-hidden="true">→</td>
                      <td className="diff-after">{formatValue(key, item.after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="amendment-effect">{option.effect}</p>
              {option.rerun_preview?.length > 0 && <p className="amendment-rerun">Re-runs: {option.rerun_preview.join(", ")}</p>}
              <button type="button" className="amendment-apply" disabled={loading} onClick={() => onChoose(option.id)}>
                Apply this amendment
              </button>
            </section>
          ))}
        </div>

        <div className="amendment-footer">
          <button type="button" className="amendment-reject" disabled={loading} onClick={onReject}>
            Reject all options
          </button>
          <span>Rejecting leaves the contract unchanged and blocks the mission.</span>
        </div>
      </div>
    </div>
  );
}
