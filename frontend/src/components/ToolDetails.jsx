import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal, ChevronDown, ChevronRight, CheckCircle2, AlertTriangle } from "lucide-react";

function toolLabel(tool) {
  const labels = {
    planning: "Planning",
    research: "Research",
    content: "Content",
    verification: "Verification",
  };
  return labels[tool] || tool || "Tool";
}

export default function ToolDetails({ executionResults = [] }) {
  const [isOpen, setIsOpen] = useState(false);
  const [expandedIndex, setExpandedIndex] = useState(null);

  if (!executionResults || executionResults.length === 0) return null;

  return (
    <div className="tool-details-container">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="tool-details-trigger"
      >
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-violet-400" />
          <span className="font-mono text-xs text-white/70">
            Execution details · {executionResults.length} step{executionResults.length > 1 ? "s" : ""}
          </span>
        </div>
        {isOpen ? (
          <ChevronDown size={15} className="text-white/50" />
        ) : (
          <ChevronRight size={15} className="text-white/50" />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="tool-details-content overflow-hidden"
          >
            <div className="pt-2 space-y-2">
              {executionResults.map((item, index) => {
                const isExpanded = expandedIndex === index;
                const failed = ["failed", "blocked", "interrupted", "stale"].includes(item.status);
                return (
                  <div key={`${item.id}-${index}`} className="tool-result-card">
                    <button
                      onClick={() =>
                        setExpandedIndex(isExpanded ? null : index)
                      }
                      className="tool-result-header"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {failed ? (
                          <AlertTriangle size={13} className="text-rose-400 shrink-0" />
                        ) : (
                          <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                        )}
                        <span className="text-xs text-white/80 font-medium truncate">
                          {item.task}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="tool-tag font-mono">
                          {toolLabel(item.tool)}
                        </span>
                        {isExpanded ? (
                          <ChevronDown size={13} className="text-white/40" />
                        ) : (
                          <ChevronRight size={13} className="text-white/40" />
                        )}
                      </div>
                    </button>

                    <AnimatePresence>
                      {isExpanded && (
                        <motion.pre
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: "auto" }}
                          exit={{ opacity: 0, height: 0 }}
                          className="tool-output-block font-mono text-[11px]"
                        >
                          {item.result}
                        </motion.pre>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
