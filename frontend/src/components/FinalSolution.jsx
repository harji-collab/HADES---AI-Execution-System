import { useState } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { Sparkles, Check, Copy, CheckCircle2 } from "lucide-react";

export default function FinalSolution({
  solution,
  mode = "AI",
  verification,
  isComplete = false,
}) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  if (!solution) return null;

  const handleCopy = async () => {
    setCopyFailed(false);
    try {
      await navigator.clipboard.writeText(solution);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyFailed(true);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="final-solution-card"
    >
      {/* HEADER BAR */}
      <div className="solution-card-header">
        <div className="flex items-center gap-2">
          <div className="solution-icon-glow">
            <Sparkles size={16} className="text-cyan-400" />
          </div>
          <span className="font-mono text-xs font-bold tracking-widest text-cyan-300 uppercase">
            ✦ FINAL SOLUTION
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="solution-mode-pill font-mono text-[10px]">
            {mode === "LOCAL" ? "LOCAL RESULT" : `${mode} SYNTHESIZED`}
          </span>

          <button
            onClick={handleCopy}
            className="copy-solution-btn"
            title="Copy solution text"
          >
            {copied ? (
              <span className="flex items-center gap-1 text-emerald-400">
                <Check size={13} />
                <span className="font-mono text-[10px]">COPIED</span>
              </span>
            ) : (
              <span className="flex items-center gap-1 text-white/60">
                <Copy size={13} />
                <span className="font-mono text-[10px]">COPY</span>
              </span>
            )}
          </button>
        </div>
      </div>
      {copyFailed && <p className="copy-feedback" role="status">Clipboard access was blocked. Select and copy the result manually.</p>}

      {/* MARKDOWN CONTENT */}
      <div className="solution-markdown-body prose prose-invert max-w-none">
        <ReactMarkdown>{solution}</ReactMarkdown>
      </div>

      {/* COMPLETION VERIFIED FOOTER */}
      {isComplete && (
        <div className="solution-verified-footer">
          <CheckCircle2 size={15} className="text-emerald-400" />
          <span className="font-mono text-xs text-emerald-300/90 font-medium">
            {verification?.passed
              ? "Requirements passed local evidence checks; factual claims were not independently validated."
              : "The mission has not passed requirement verification."}
          </span>
        </div>
      )}
    </motion.div>
  );
}
