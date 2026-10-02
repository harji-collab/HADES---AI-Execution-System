import { useEffect, useRef } from "react";
import { Download, Hash, ListChecks, Network, Radio } from "lucide-react";

const STATUS_LABELS = {
  satisfied: "SATISFIED",
  stale: "STALE",
  failed: "FAILED",
  blocked: "BLOCKED",
  running: "RUNNING",
  pending: "PENDING",
  complete: "COMPLETE",
};

function Dot({ status }) {
  return <span className={`board-dot dot-${status}`} aria-hidden="true" />;
}

function latestByStep(evidence) {
  const latest = {};
  const runs = {};
  for (const item of evidence) {
    latest[item.step] = item;
    (runs[item.step] ||= []).push(item);
  }
  return { latest, runs };
}

function normalizeTaskStatus(status) {
  if (status === "complete" || status === "stale" || status === "running") return status;
  if (status === "failed" || status === "blocked" || status === "interrupted") return "failed";
  return "pending";
}

/** Derive every status the board shows from the mission record, the latest
 * verification and live task events, so all three columns agree. */
function deriveBoard({ mission, verification, evidence = [], taskLive = {} }) {
  const specs = mission?.contract?.requirement_specs || [];
  const steps = (mission?.steps || []).filter((step) => step.tool !== "verification");
  const { latest, runs } = latestByStep(evidence);
  const taskStatus = Object.fromEntries(steps.map((step) => [
    step.id,
    normalizeTaskStatus(taskLive[step.id]?.status || latest[step.id]?.status),
  ]));
  const results = Object.fromEntries((verification?.requirement_results || []).map((item) => [item.requirement_id, item]));
  const blocked = mission?.status === "blocked";

  const requirements = specs.map((spec) => {
    const tasks = steps.filter((step) => (step.requirements || []).includes(spec.id));
    const result = results[spec.id];
    const states = tasks.map((task) => taskStatus[task.id]);
    let status;
    if (states.includes("running")) status = "running";
    else if (states.includes("stale") || result?.status === "stale") status = "stale";
    else if (result?.status === "satisfied") status = "satisfied";
    else if (result) status = blocked ? "blocked" : "failed";
    else status = "pending";
    return { spec, tasks, result, status };
  });

  return {
    requirements,
    steps,
    taskStatus,
    latest,
    runs,
    satisfied: requirements.filter((item) => item.status === "satisfied").length,
    staleNow: Object.values(taskStatus).filter((status) => status === "stale").length,
  };
}

function StatsBar({ board, mission, onDownloadReceipt, receiptBusy }) {
  const llm = mission?.llm_calls || {};
  const rerun = mission?.reexecution;
  return (
    <div className="board-stats">
      <div className="board-stat">
        <span>Requirements</span>
        <strong>{board.satisfied}/{board.requirements.length}</strong>
        <small>satisfied</small>
      </div>
      <div className="board-stat">
        <span>Re-executed</span>
        <strong>{rerun ? `${rerun.rerun}/${rerun.total}` : "—"}</strong>
        <small>{rerun ? "tasks, last change" : "no changes yet"}</small>
      </div>
      <div className={`board-stat ${board.staleNow ? "stat-stale" : ""}`}>
        <span>Stale</span>
        <strong>{board.staleNow}</strong>
        <small>tasks awaiting re-run</small>
      </div>
      <div className="board-stat board-stat-llm">
        <span>LLM calls</span>
        <div className="llm-phases">
          {["planning", "execution", "recovery", "verification"].map((phase) => (
            <span key={phase} className={phase === "verification" ? "llm-verification" : ""}>
              {phase.slice(0, 1).toUpperCase() + phase.slice(1)} <b>{llm[phase] || 0}</b>
            </span>
          ))}
        </div>
      </div>
      <button type="button" className="board-receipt-btn" onClick={onDownloadReceipt} disabled={!mission?.id || receiptBusy}>
        <Download size={14} /> {receiptBusy ? "Preparing…" : "Download receipt"}
      </button>
    </div>
  );
}

function ContractChecklist({ board, mission }) {
  const params = mission?.contract?.parameters || {};
  const amendments = mission?.contract?.amendments || [];
  return (
    <section className="board-column">
      <h3 className="board-heading"><ListChecks size={14} /> Contract</h3>
      <dl className="board-params">
        {Object.entries(params).filter(([, value]) => value != null).map(([key, value]) => (
          <div key={key}><dt>{key}</dt><dd>{key === "max_budget" ? `₹${Number(value).toLocaleString("en-IN")}` : String(value)}</dd></div>
        ))}
      </dl>
      <ul className="board-checklist">
        {board.requirements.map(({ spec, result, status }) => (
          <li key={spec.id} className={`board-req req-${status}`}>
            <div className="board-req-title"><Dot status={status} /><span>{spec.description}</span></div>
            <div className="board-req-meta">
              <span className={`board-badge badge-${status}`}>{STATUS_LABELS[status]}</span>
              <code>{spec.verifier}</code>
            </div>
            {result?.reason && <p className="board-req-reason">{result.reason}</p>}
          </li>
        ))}
      </ul>
      {amendments.length > 0 && (
        <div className="board-amendments">
          <span className="flow-eyebrow">Amendments</span>
          {amendments.map((item) => <p key={item.approved_at}>{item.label}</p>)}
        </div>
      )}
    </section>
  );
}

function DependencyView({ board }) {
  return (
    <section className="board-column">
      <h3 className="board-heading"><Network size={14} /> Requirement → tasks → evidence</h3>
      <ol className="board-deps">
        {board.requirements.map(({ spec, tasks, status }) => (
          <li key={spec.id} className="board-dep-req">
            <div className="board-dep-head"><Dot status={status} /><strong>{spec.id}</strong><span>{spec.type}</span></div>
            <ul className="board-dep-tasks">
              {tasks.map((task) => {
                const taskStatus = board.taskStatus[task.id];
                const evidence = board.latest[task.id];
                const history = board.runs[task.id] || [];
                return (
                  <li key={task.id} className={`board-task task-${taskStatus}`}>
                    <div className="board-task-head">
                      <Dot status={taskStatus} />
                      <span className="board-task-title">{task.title}</span>
                      {task.reads?.length > 0 && <span className="board-reads">reads {task.reads.join(", ")}</span>}
                    </div>
                    {evidence && (
                      <div className="board-evidence">
                        <span className={`board-evidence-id ev-${normalizeTaskStatus(evidence.status)}`}>
                          {history.length > 1 ? history.map((item) => item.id).join(" → ") : evidence.id}
                        </span>
                        <span className="board-evidence-output">{(evidence.output || "").split("\n")[0]}</span>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>
      <div className="board-legend">
        {["complete", "running", "stale", "failed", "pending"].map((status) => (
          <span key={status}><Dot status={status} /> {status}</span>
        ))}
      </div>
    </section>
  );
}

function EventStream({ auditEvents, liveEvents }) {
  const listRef = useRef(null);
  const items = [
    ...auditEvents.map((entry) => ({ key: `a-${entry.sequence}`, kind: entry.kind, message: entry.message, time: entry.time, hash: entry.hash })),
    ...liveEvents.map((entry, index) => ({ key: `l-${index}`, ...entry, live: true })),
  ];
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [items.length]);
  return (
    <section className="board-column">
      <h3 className="board-heading"><Radio size={14} /> Event stream</h3>
      <ol className="board-events" ref={listRef}>
        {items.map((item) => (
          <li key={item.key} className={`board-event ${item.live ? "event-live" : ""} event-${item.kind}`}>
            <div className="board-event-head">
              <span className="board-event-kind">{item.kind}</span>
              <time>{item.time ? new Date(item.time).toLocaleTimeString() : ""}</time>
            </div>
            <p>{item.message}</p>
            {item.hash && <span className="board-event-hash" title={item.hash}><Hash size={10} />{item.hash.slice(0, 10)}</span>}
          </li>
        ))}
      </ol>
      <p className="board-footnote">Audit events are SHA-256 hash-chained; live events are replaced by the audit log when a run finishes.</p>
    </section>
  );
}

export default function MissionBoard({ mission, verification, evidence, taskLive, auditEvents, liveEvents, onDownloadReceipt, receiptBusy }) {
  const board = deriveBoard({ mission, verification, evidence, taskLive });
  if (!board.requirements.length) return null;
  return (
    <section className="mission-board" aria-label="Mission board">
      <StatsBar board={board} mission={mission} onDownloadReceipt={onDownloadReceipt} receiptBusy={receiptBusy} />
      <div className="board-grid">
        <ContractChecklist board={board} mission={mission} />
        <DependencyView board={board} />
        <EventStream auditEvents={auditEvents} liveEvents={liveEvents} />
      </div>
    </section>
  );
}
