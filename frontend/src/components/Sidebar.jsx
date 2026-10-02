import { Sparkles, History, FolderKanban, Settings, Plus, X, Bot } from "lucide-react";

export default function Sidebar({ onNewMission, onClose, onNavigate, activeView = "mission", isMobile = false }) {
  return (
    <div className="sidebar-container">
      {/* BRAND */}
      <div className="sidebar-brand">
        <div className="brand-logo-orb">
          <Bot size={18} className="text-violet-400" />
          <div className="brand-logo-glow" />
        </div>
        <div className="flex flex-col">
          <span className="brand-title">HADES</span>
          <span className="brand-tagline font-mono">EXECUTION WORKSPACE</span>
        </div>
        {isMobile && onClose && (
          <button onClick={onClose} className="sidebar-close-btn" aria-label="Close sidebar">
            <X size={16} />
          </button>
        )}
      </div>

      {/* NEW MISSION BUTTON */}
      <button onClick={onNewMission} className="new-mission-btn">
        <Plus size={15} />
        <span>New Mission</span>
      </button>

      {/* NAV SECTION */}
      <nav className="sidebar-nav">
        <div className="nav-group-label">WORKSPACE</div>
        
        <button onClick={() => onNavigate?.("mission")} className={`nav-item ${activeView === "mission" ? "active" : ""}`}>
          <Sparkles size={15} className="nav-icon" />
          <span>Active Mission</span>
        </button>

        <button onClick={() => onNavigate?.("history")} className={`nav-item ${activeView === "history" ? "active" : ""}`}>
          <History size={15} className="nav-icon" />
          <span>Mission History</span>
        </button>

        <button onClick={() => onNavigate?.("workspace")} className={`nav-item ${activeView === "workspace" ? "active" : ""}`}>
          <FolderKanban size={15} className="nav-icon" />
          <span>Workspace</span>
        </button>

        <div className="nav-group-label mt-6">PREFERENCES</div>

        <button onClick={() => onNavigate?.("settings")} className={`nav-item ${activeView === "settings" ? "active" : ""}`}>
          <Settings size={15} className="nav-icon" />
          <span>Settings</span>
        </button>
      </nav>

      {/* STATUS FOOTER */}
      <div className="sidebar-status-card">
        <div className="status-dot-pulse">
          <span className="dot-core" />
          <span className="dot-ring" />
        </div>
        <div className="flex flex-col min-w-0">
          <span className="status-title font-mono">HADES CORE</span>
          <span className="status-subtitle">ONLINE • STANDBY</span>
        </div>
      </div>
    </div>
  );
}
