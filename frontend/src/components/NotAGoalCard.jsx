import { MessageCircle, Play } from "lucide-react";

// Reply for input that is not a goal: no mission is created and nothing is
// blocked. Optional LLM quick answers are labeled so nobody mistakes them for
// verified mission output.
export default function NotAGoalCard({ reply, onExample, disabled = false }) {
  return (
    <div className="not-goal-card">
      <div className="answer-status not-goal-status">
        <MessageCircle size={14} />
        <span>{reply.kind === "QUESTION" ? "QUESTION · NO MISSION CREATED" : "CHAT · NO MISSION CREATED"}</span>
      </div>
      <p className="answer-text">{reply.message}</p>

      {reply.quick_answer && (
        <div className="quick-answer">
          <span>{reply.quick_answer_label || "Quick answer (not a mission)"}</span>
          <p>{reply.quick_answer}</p>
        </div>
      )}

      <p className="not-goal-hint">Try a goal instead:</p>
      <div className="not-goal-examples">
        {(reply.examples || []).map((example) => (
          <button key={example} type="button" disabled={disabled} onClick={() => onExample(example)}>
            <Play size={12} />
            <span>{example}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
