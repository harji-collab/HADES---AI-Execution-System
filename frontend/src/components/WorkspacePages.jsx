import { Activity, ArrowUpRight, CircleCheck, CircleX, Clock3, FolderOpen, RefreshCw, Server } from "lucide-react";

function PageShell({ eyebrow, title, description, loading, error, onRefresh, children }) {
  return (
    <section className="utility-page">
      <div className="utility-page-heading">
        <div className="min-w-0">
          <p className="utility-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p className="utility-description">{description}</p>
        </div>
        <button type="button" className="utility-refresh-btn" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          <span>{loading ? "Refreshing" : "Refresh"}</span>
        </button>
      </div>
      {error && <div className="utility-error" role="alert">{error}</div>}
      {children}
    </section>
  );
}

export function MissionHistoryPage({ missions = [], loading, error, onRefresh, onSelect }) {
  return (
    <PageShell eyebrow="MISSION ARCHIVE" title="Mission History" description="Reopen missions and inspect their verified result, evidence, and audit timeline." loading={loading} error={error} onRefresh={onRefresh}>
      {missions.length ? (
        <div className="utility-list">
          {missions.slice().reverse().map((mission) => (
            <button type="button" key={mission.id} className="utility-list-row" onClick={() => onSelect(mission.id)}>
              <span className="utility-list-icon"><Clock3 size={16} /></span>
              <span className="utility-list-main">
                <strong>{mission.goal}</strong>
                <small>{mission.id} · {mission.requirements} requirement{mission.requirements === 1 ? "" : "s"} · {mission.evidence} evidence record{mission.evidence === 1 ? "" : "s"}</small>
              </span>
              <span className={`utility-status status-${mission.status}`}>{mission.status?.replaceAll("_", " ")}</span>
              <ArrowUpRight size={15} className="text-white/35" />
            </button>
          ))}
        </div>
      ) : !loading && <div className="utility-empty">No missions in this backend session yet. Start a mission or run the demo.</div>}
    </PageShell>
  );
}

export function WorkspacePage({ snapshot, loading, error, onRefresh }) {
  const files = snapshot?.files || [];
  return (
    <PageShell eyebrow="LOCAL CONTEXT" title="Workspace" description={snapshot?.root || "Inspect the workspace snapshot available to mission tools."} loading={loading} error={error} onRefresh={onRefresh}>
      <div className="utility-summary-card">
        <FolderOpen size={18} className="text-cyan-300" />
        <span><strong>{files.length}</strong> files in the current snapshot</span>
      </div>
      <div className="utility-list workspace-file-list">
        {files.map((file) => (
          <div className="workspace-file-row" key={file.path}>
            <code>{file.path}</code>
            <span>{Number(file.size || 0).toLocaleString()} bytes</span>
          </div>
        ))}
        {!files.length && !loading && <div className="utility-empty">The workspace scan returned no files.</div>}
      </div>
    </PageShell>
  );
}

export function SettingsPage({ health, loading, error, onRefresh }) {
  return (
    <PageShell eyebrow="SYSTEM STATUS" title="Settings" description="Connection and provider availability for this HADES session." loading={loading} error={error} onRefresh={onRefresh}>
      <div className="settings-status-grid">
        <div className="utility-summary-card">
          {health?.status === "healthy" ? <CircleCheck size={18} className="text-emerald-300" /> : <CircleX size={18} className="text-rose-300" />}
          <span><strong>Backend</strong><small>{health?.status || "Not checked"}{health?.version ? ` · v${health.version}` : ""}</small></span>
        </div>
        <div className="utility-summary-card"><Activity size={18} className="text-violet-300" /><span><strong>Planning</strong><small>Local-first and deterministic</small></span></div>
        <div className="utility-summary-card"><Server size={18} className="text-cyan-300" /><span><strong>Gemini</strong><small>{health?.gemini ? "Configured · optional" : "Unavailable · local fallback active"}</small></span></div>
        <div className="utility-summary-card"><Server size={18} className="text-cyan-300" /><span><strong>Groq</strong><small>{health?.groq ? "Configured · optional" : "Unavailable · local fallback active"}</small></span></div>
      </div>
      <p className="settings-note">The guided demo uses local deterministic execution and does not call Gemini or Groq.</p>
    </PageShell>
  );
}
