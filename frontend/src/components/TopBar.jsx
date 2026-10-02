import { Menu, ShieldCheck, Cpu } from "lucide-react";

export default function TopBar({ onOpenSidebar, activeMissionGoal, apiStatus = "CHECKING" }) {
  return (
    <header className="topbar-glass">
      <div className="topbar-left">
        <button
          onClick={onOpenSidebar}
          className="mobile-menu-trigger"
          aria-label="Open Menu"
        >
          <Menu size={18} />
        </button>

        <div className="topbar-brand">
          <div className="topbar-logo-icon">
            <Cpu size={16} className="text-cyan-400" />
          </div>
          <span className="topbar-title">HADES</span>
        </div>
      </div>

      {activeMissionGoal && (
        <div className="topbar-center max-w-xs md:max-w-md truncate hidden sm:flex items-center gap-2 px-3 py-1 rounded-full glass-pill">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-xs text-white/70 truncate font-sans">
            {activeMissionGoal}
          </span>
        </div>
      )}

      <div className="topbar-right">
        <div className={`status-badge-online status-badge-${apiStatus.toLowerCase()}`} role="status" aria-label={`Backend ${apiStatus.toLowerCase()}`}>
          <span className="online-indicator-dot" />
          <span className="font-mono text-[11px] tracking-wider">{apiStatus}</span>
        </div>

        <div className="hitl-badge">
          <ShieldCheck size={13} className="text-violet-400" />
          <span className="font-mono text-[10px] text-violet-300/80 uppercase tracking-widest hidden md:inline">
            Human-in-the-Loop
          </span>
        </div>
      </div>
    </header>
  );
}
