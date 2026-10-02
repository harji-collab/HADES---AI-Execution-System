import { motion } from "framer-motion";
import { Bot, User } from "lucide-react";

export function UserMessage({ text }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="message-row user-row"
    >
      <div className="user-message-bubble">
        <p className="user-message-text">{text}</p>
      </div>
      <div className="user-avatar-orb">
        <User size={14} className="text-cyan-300" />
      </div>
    </motion.div>
  );
}

export function AssistantMessage({ children, className = "" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`message-row assistant-row ${className}`}
    >
      <div className="assistant-avatar-orb">
        <Bot size={16} className="text-violet-400" />
        <div className="avatar-aura-glow" />
      </div>

      <div className="assistant-content-area">
        <div className="assistant-header-label font-mono">
          <span className="assistant-name">HADES</span>
          <span className="assistant-role">EXECUTION AGENT</span>
        </div>
        <div className="assistant-body">
          {children}
        </div>
      </div>
    </motion.div>
  );
}
