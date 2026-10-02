import { useState, useRef, useEffect } from "react";
import { ArrowUp, Cpu, RotateCcw, Sparkles } from "lucide-react";

export default function ChatComposer({
  goal,
  setGoal,
  onSubmit,
  loading = false,
  hasActiveMission = false,
  onReset,
  placeholder,
}) {
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef(null);

  // Auto-resize textarea height as user types
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        180
      )}px`;
    }
  }, [goal]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!loading && goal.trim()) {
        onSubmit();
      }
    }
  };

  return (
    <div className="composer-wrapper">
      <div className={`composer-floating-box ${isFocused ? "focused" : ""}`}>
        {/* INNER AMBIENT REFLECTION GLOW */}
        <div className="composer-ambient-glow" />

        <div className="composer-input-row">
          <textarea
            ref={textareaRef}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            disabled={loading}
            rows={1}
            placeholder={
              loading
                ? "HADES is executing mission..."
                : placeholder || "Give HADES a goal..."
            }
            className="composer-textarea"
          />
        </div>

        {/* BOTTOM CONTROLS & HINTS */}
        <div className="composer-bottom-bar">
          <div className="composer-hint-text font-mono">
            <span>Enter to execute</span>
            <span className="hint-sep">•</span>
            <span>Shift + Enter for new line</span>
          </div>

          <div className="composer-action-group">
            {hasActiveMission && !loading && (
              <button
                type="button"
                onClick={onReset}
                className="composer-reset-btn"
                title="New Mission"
              >
                <RotateCcw size={15} />
                <span className="font-mono text-xs hidden sm:inline">New Mission</span>
              </button>
            )}

            <button
              type="button"
              onClick={onSubmit}
              disabled={loading || !goal.trim()}
              className="composer-send-btn"
              title="Execute Goal"
            >
              {loading ? (
                <Cpu size={18} className="animate-spin text-cyan-300" />
              ) : (
                <div className="flex items-center gap-1">
                  <Sparkles size={14} className="text-cyan-300 hidden sm:inline" />
                  <ArrowUp size={18} />
                </div>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="composer-disclaimer font-mono">
        HADES plans before execution • Human authorization in control
      </div>
    </div>
  );
}
