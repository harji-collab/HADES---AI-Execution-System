import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, Sparkles, FileText, AlertTriangle, Plane } from "lucide-react";

import ThreeBackground from "./components/ThreeBackground";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { UserMessage, AssistantMessage } from "./components/ChatMessage";
import ExecutionPlan from "./components/ExecutionPlan";
import ApprovalControl from "./components/ApprovalControl";
import ExecutionStatus from "./components/ExecutionStatus";
import ToolDetails from "./components/ToolDetails";
import ChatComposer from "./components/ChatComposer";
import AmendmentModal from "./components/AmendmentModal";
import MissionBoard from "./components/MissionBoard";
import AnswerCard from "./components/AnswerCard";
import NotAGoalCard from "./components/NotAGoalCard";
import { EvidencePanel, MissionProgress, VerificationPanel } from "./components/MissionPanels";
import { MissionHistoryPage, SettingsPage, WorkspacePage } from "./components/WorkspacePages";

import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "/api");
const DEMO_GOAL = "Create a 3 item checklist for a reliable HADES hackathon demo";
const TRIP_GOAL = "Get me ready for my Bengaluru trip on Friday: check the weather, build a packing list, add it to my calendar, draft a leave email to my manager, keep total cost under ₹4,000";

const defaultStages = [
  { id: 1, title: "Understanding objective", status: "idle" },
  { id: 2, title: "Building execution plan", status: "idle" },
  { id: 3, title: "Executing tools & tasks", status: "idle" },
  { id: 4, title: "Verifying final result", status: "idle" },
];

function updateStage(stages, id, status) {
  return stages.map((stage) =>
    stage.id === id ? { ...stage, status } : stage
  );
}

function isProbablyLocalPlan(plan) {
  if (!plan?.steps?.length) return true;
  // Typed missions declare their tools: everything writes local files, and
  // the only network access is a read-only forecast lookup.
  if (plan.contract?.requirement_specs?.length) return true;
  const externalWords = [
    "browser",
    "web",
    "internet",
    "external",
    "email",
    "send",
    "post",
    "publish",
    "device",
    "payment",
    "purchase",
    "delete",
    "modify",
    "write",
    "upload",
  ];
  const serialized = JSON.stringify(plan).toLowerCase();
  return !externalWords.some((word) => serialized.includes(word));
}

const CHANGEABLE_STATUSES = new Set(["complete", "recovery_required", "blocked"]);
const CHANGE_WORDS = /\b(moved?|moving|reschedul\w*|postpon\w*|prepon\w*|shift\w*|chang\w*|instead|switch\w*|now on|raise|increase|lower)\b/i;

function describeDiff(diff = {}) {
  return Object.entries(diff).map(([key, item]) => `${key}: ${item.before ?? "—"} → ${item.after}`).join(" · ");
}

async function readJsonResponse(response, fallbackMessage) {
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
  if (!response.ok || data.status === "error") {
    const detail = data.detail || data.message;
    const message = Array.isArray(detail) ? detail.map((item) => item.msg).join(" · ") : detail;
    throw new Error(message || `${fallbackMessage} (HTTP ${response.status})`);
  }
  return data;
}

export default function App() {
  const [goal, setGoal] = useState("");
  const [submittedGoal, setSubmittedGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState(null);
  const [finalSolution, setFinalSolution] = useState("");
  const [solutionMode, setSolutionMode] = useState("");
  const [error, setError] = useState("");
  const [executionResults, setExecutionResults] = useState([]);
  const [verification, setVerification] = useState(null);
  const [recovery, setRecovery] = useState(null);
  const [approvalRequired, setApprovalRequired] = useState(false);
  const [result, setResult] = useState("");
  const [stages, setStages] = useState(defaultStages);
  const [showSidebar, setShowSidebar] = useState(false);
  const [auditEvents, setAuditEvents] = useState([]);
  const [missionRecord, setMissionRecord] = useState(null);
  const [missionPhase, setMissionPhase] = useState("IDLE");
  const [activeView, setActiveView] = useState("mission");
  const [viewData, setViewData] = useState(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [viewError, setViewError] = useState("");
  const [apiStatus, setApiStatus] = useState("CHECKING");
  const [changeLog, setChangeLog] = useState([]);
  const [chatReplies, setChatReplies] = useState([]);
  const [pendingInput, setPendingInput] = useState("");
  const [amendmentHidden, setAmendmentHidden] = useState(false);
  const [taskLive, setTaskLive] = useState({});
  const [liveEvents, setLiveEvents] = useState([]);
  const [receiptBusy, setReceiptBusy] = useState(false);
  const activeRequest = useRef(null);
  const footerRef = useRef(null);

  // The composer and approval dock float over the page; publish the
  // composer's real height so content and the dock can clear it.
  useEffect(() => {
    const footer = footerRef.current;
    if (!footer || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      document.documentElement.style.setProperty("--composer-h", `${Math.ceil(entry.target.getBoundingClientRect().height)}px`);
    });
    observer.observe(footer);
    return () => observer.disconnect();
  }, []);

  // Chat-style composer: slide it away while scrolling down so the page
  // below is fully visible; bring it back on any upward scroll or at the top.
  const [composerHidden, setComposerHidden] = useState(false);
  useEffect(() => {
    let lastY = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const y = window.scrollY;
        if (y < 80) setComposerHidden(false);
        else if (y > lastY + 6) setComposerHidden(true);
        else if (y < lastY - 6) setComposerHidden(false);
        lastY = y;
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function scrollToEvidence() {
    document.getElementById("mission-evidence")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function scrollToAnswer() {
    window.scrollTo({ top: 0, behavior: "smooth" });
    setComposerHidden(false);
  }

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error("Backend is unavailable"); return response.json(); })
      .then((health) => setApiStatus(health.status === "healthy" ? "ONLINE" : "OFFLINE"))
      .catch((err) => { if (err.name !== "AbortError") setApiStatus("OFFLINE"); });
    return () => controller.abort();
  }, []);

  function beginRequest(timeoutMs) {
    activeRequest.current?.abort();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new DOMException("The request timed out. Please try again.", "TimeoutError")), timeoutMs);
    activeRequest.current = controller;
    return {
      signal: controller.signal,
      cleanup: () => {
        clearTimeout(timer);
        if (activeRequest.current === controller) activeRequest.current = null;
      },
    };
  }

  async function refreshAudit(missionId = plan?.id) {
    if (!missionId) return;
    try {
      const response = await fetch(`${API_URL}/mission/${encodeURIComponent(missionId)}`, { signal: AbortSignal.timeout(8000) });
      if (!response.ok) return;
      const mission = await response.json();
      setAuditEvents(mission.events || []);
      setLiveEvents([]);
      setTaskLive({});
      setMissionRecord(mission);
      setEvidenceRecords(mission.evidence || []);
      setRecovery(mission.recovery || null);
      setVerification(mission.verification || null);
      if (mission.artifacts?.length) setFinalSolution(mission.artifacts.at(-1));
      setPlan((current) => current?.id === missionId ? mission : current);
    } catch (err) {
      console.warn("Mission audit timeline could not be refreshed.", err);
    }
  }

  const isLocalPlan = isProbablyLocalPlan(plan);

  const [evidenceRecords, setEvidenceRecords] = useState([]);

  function clearMissionState() {
    setPlan(null);
    setMissionRecord(null);
    setEvidenceRecords([]);
    setFinalSolution("");
    setSolutionMode("");
    setExecutionResults([]);
    setVerification(null);
    setRecovery(null);
    setAuditEvents([]);
    setApprovalRequired(false);
    setResult("");
    setChangeLog([]);
    setChatReplies([]);
    setTaskLive({});
    setLiveEvents([]);
  }

  async function generatePlan({ demoMode = false, goalText } = {}) {
    const currentGoal = demoMode ? DEMO_GOAL : (goalText ?? goal).trim();
    if (!currentGoal || loading) return;

    // Like a chat app: the sent message moves into the conversation. The
    // current mission stays on screen until the backend confirms this is a
    // new goal; questions and chat get a reply without replacing it.
    setActiveView("mission");
    setGoal("");
    setPendingInput(currentGoal);
    setLoading(true);
    setError("");

    let request;
    try {
      // Optional LLM decomposition can take up to two 8s provider timeouts.
      request = beginRequest(25000);
      const response = await fetch(`${API_URL}${demoMode ? "/demo/plan" : "/plan"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        ...(demoMode ? {} : { body: JSON.stringify({ goal: currentGoal }) }),
        signal: request.signal,
      });
      const data = await readJsonResponse(response, "HADES could not create an execution plan.");
      if (data.status === "not_a_goal") {
        setChatReplies((prev) => [...prev, { text: currentGoal, reply: data }]);
        return;
      }

      scrollToAnswer();
      clearMissionState();
      setSubmittedGoal(currentGoal);
      setStages(defaultStages.map((s) => ({ ...s, status: s.id <= 2 ? "complete" : "idle" })));
      setPlan(data.plan);
      setMissionRecord(data.plan);
      setAuditEvents(data.plan.events || []);
      setMissionPhase("READY");
      setApprovalRequired(true);
      setTimeout(() => setMissionPhase((current) => current === "READY" ? "APPROVAL" : current), 650);
    } catch (err) {
      if (err.name === "AbortError" && !activeRequest.current) return;
      console.error(err);
      setError(
        err.name === "TimeoutError"
          ? "Planning took too long. Please try again."
          : err.message || "Something went wrong while creating the execution plan."
      );
    } finally {
      request?.cleanup();
      setPendingInput("");
      setLoading(false);
    }
  }

  async function consumeMissionStream(response, { recoveryOnly = false } = {}) {
    if (!response.ok) await readJsonResponse(response, "Mission execution failed.");
    if (!response.body) throw new Error("The execution stream is unavailable.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let sawComplete = false;
    if (recoveryOnly) setMissionPhase("RE-EXECUTION");

    const handleEvent = (eventBlock) => {
      const lines = eventBlock.split(/\r?\n/);
      const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const jsonString = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
      if (!jsonString) return;
      let parsed;
      try { parsed = JSON.parse(jsonString); } catch { return; }
      const type = parsed.type || eventName;
      const data = parsed.data ?? parsed;
      const task = data?.task || data;
      const pushLive = (message) => setLiveEvents((prev) => [...prev, { kind: type, message, time: new Date().toISOString() }]);

      if ((type === "task_start" || type === "task_complete" || type === "task_failed") && task?.id && task.tool !== "verification") {
        const status = type === "task_start" ? "running" : type === "task_complete" ? "complete" : "failed";
        setTaskLive((prev) => ({ ...prev, [task.id]: { status } }));
      }
      if (type === "task_start") pushLive(`▶ ${task.title || task.id}`);
      if (type === "task_complete") pushLive(`✓ ${task.title || task.id}: ${(data.output || "").split("\n")[0].slice(0, 140)}`);
      if (type === "task_failed") pushLive(`✗ ${task.title || task.id}: ${(data.reason || data.output || "").slice(0, 160)}`);
      if (type === "change") pushLive(`${describeDiff(data.change?.diff)} · ${data.change?.stale_evidence?.length || 0} evidence stale · ${data.change?.message}`);
      if (type === "amendment") pushLive(`Amendment approved: ${data.amendment?.label} · ${data.change?.message}`);
      if (type === "recovery") pushLive(data.message || "Recovery started.");
      if (type === "recovery_required") pushLive(data.recovery?.kind === "amendment" ? "Constraint failed: contract amendment required." : "Verification failed: recovery required.");
      if (type === "blocked") pushLive(data.recovery?.reason || "Mission blocked.");
      if (type === "verification") pushLive(data.verification?.passed ? "Verification passed." : "Verification failed.");
      if (type === "complete") {
        pushLive(`Run finished: ${data.status}.`);
        if (data.llm_calls) setMissionRecord((prev) => prev ? { ...prev, llm_calls: data.llm_calls } : prev);
      }

      if (type === "mission" || type === "plan") {
        const record = data.mission || data.plan;
        if (record) setMissionRecord(record);
      }
      if (type === "change") {
        const change = data.change || {};
        if (data.mission) {
          setMissionRecord(data.mission);
          setPlan(data.mission);
          setEvidenceRecords(data.mission.evidence || []);
          setVerification(data.mission.verification || null);
        }
        setRecovery(null);
        setChangeLog((prev) => prev.map((entry, index) => index === prev.length - 1 ? { ...entry, change } : entry));
        setResult(`${describeDiff(change.diff)}. ${change.stale_evidence?.length || 0} evidence record(s) stale. ${change.message}.`);
        setMissionPhase("RE-EXECUTION");
      }
      if (type === "amendment") {
        const change = data.change || {};
        if (data.mission) {
          setMissionRecord(data.mission);
          setPlan(data.mission);
          setEvidenceRecords(data.mission.evidence || []);
          setVerification(data.mission.verification || null);
          setRecovery(data.mission.recovery || null);
        }
        setChangeLog((prev) => [...prev, { text: `Approved amendment: ${data.amendment?.label}`, change }]);
        setResult(`Contract amended (${describeDiff(change.diff)}). ${change.message}.`);
        setMissionPhase("RE-EXECUTION");
      }
      if (type === "recovery" && data.approval_required === false) {
        setRecovery(null);
        setResult(data.message || "Retrying failed tasks inside the contract.");
        setMissionPhase("RE-EXECUTION");
      }
      if (type === "task_start") {
        setMissionPhase(task.tool === "verification" ? recoveryOnly ? "RE-VERIFYING" : "VERIFYING" : recoveryOnly ? "RE-EXECUTION" : "EXECUTING");
        setStages((prev) => {
          let next = updateStage(prev, 3, "running");
          if (task.tool === "verification") next = updateStage(next, 4, "running");
          return next;
        });
      }
      if (type === "task_complete" || type === "task_failed") {
        setExecutionResults((prev) => [...prev, {
          id: `${task.id || task.tool}-${prev.length}`,
          task: task.title || task.task || task.id || task.tool,
          tool: task.tool,
          provider: data.provider,
          result: data.output || data.reason || "No tool output was returned.",
          status: type === "task_failed" ? "failed" : "complete",
        }]);
        if (task.tool === "verification" && type === "task_complete") setStages((prev) => updateStage(prev, 4, "complete"));
        if (type === "task_failed" && task.tool === "verification") setStages((prev) => updateStage(prev, 4, "error"));
      }
      if (type === "recovery_required") {
        setRecovery(data.recovery || null);
        setMissionPhase("RECOVERY REQUIRED");
        if (data.recovery?.kind === "amendment") {
          setAmendmentHidden(false);
          setResult("A contract constraint cannot be met as written. Choose a contract amendment or reject all options.");
        } else {
          setResult("Verification failed. Review the missing requirement, then approve targeted recovery.");
        }
      }
      if (type === "blocked") {
        setRecovery(data.recovery || null);
        setMissionPhase("BLOCKED");
        setResult("Mission blocked because its requirements remain unmet.");
      }
      if (type === "solution") {
        setFinalSolution(data.solution && data.solution !== "No deliverable produced." ? data.solution : "");
        setSolutionMode(data.mode || "LOCAL");
      }
      if (type === "verification") {
        const result = data.verification || null;
        setVerification(result);
        if (result?.passed) setMissionPhase("VERIFIED RESULT");
        else if (result) setMissionPhase("RECOVERY REQUIRED");
      }
      if (type === "complete") {
        sawComplete = true;
        if (data.final_solution) setFinalSolution(data.final_solution);
        if (data.solution_mode) setSolutionMode(data.solution_mode);
        if (data.status === "complete") {
          setRecovery((current) => current?.status === "approval_required" ? current : null);
          setMissionPhase("VERIFIED RESULT");
          setResult("Mission completed successfully. Requirements passed verification.");
        } else if (data.status === "blocked") {
          setMissionPhase("BLOCKED");
          setResult("Mission is blocked because its requirements remain unmet.");
        } else if (data.status === "recovery_required") {
          setMissionPhase("RECOVERY REQUIRED");
          setResult(data.recovery?.kind === "amendment"
            ? "A contract constraint cannot be met as written. Choose a contract amendment or reject all options."
            : "Verification failed. A targeted recovery plan needs your approval.");
        }
        setStages((prev) => {
          let next = updateStage(prev, 3, data.status === "blocked" ? "error" : "complete");
          return updateStage(next, 4, data.status === "complete" ? "complete" : "error");
        });
      }
      if (type === "error") throw new Error(data.message || "Mission execution failed.");
    };

    try {
      while (true) {
        let timeoutId;
        let chunk;
        try {
          chunk = await Promise.race([
            reader.read(),
            new Promise((_, reject) => { timeoutId = setTimeout(() => reject(new Error("HADES stopped responding. The mission stream was cancelled.")), 30000); }),
          ]);
        } finally { clearTimeout(timeoutId); }
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || "";
        blocks.forEach(handleEvent);
      }
      buffer += decoder.decode();
      if (buffer.trim()) handleEvent(buffer);
      if (!sawComplete) throw new Error("The mission stream ended before HADES reported a final state.");
    } catch (streamError) {
      await reader.cancel().catch(() => {});
      throw streamError;
    }
  }

  async function approveAndExecute() {
    if (!plan || loading) return;

    setLoading(true);
    setError("");
    setApprovalRequired(false);
    setExecutionResults([]);
    setVerification(null);
    setRecovery(null);
    setFinalSolution("");
    setSolutionMode("");
    setResult("");
    setStages((prev) => updateStage(prev, 3, "running"));
    setMissionPhase("EXECUTING");
    scrollToAnswer();

    let request;
    try {
      request = beginRequest(90000);
      const response = await fetch(`${API_URL}/execute-approved-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: submittedGoal || goal.trim(), plan, approved: true }),
        signal: request.signal,
      });
      await consumeMissionStream(response);
      await refreshAudit(plan.id);
    } catch (err) {
      if (err.name === "AbortError" && !activeRequest.current) return;
      console.error(err);
      setError(err.message || "Something went wrong during execution.");
      setMissionPhase("INTERRUPTED");
      await refreshAudit(plan.id);
      setStages((prev) =>
        prev.map((s) => (s.status === "running" ? { ...s, status: "error" } : s))
      );
    } finally {
      request?.cleanup();
      setLoading(false);
    }
  }

  async function approveRecoveryAndExecute(approved) {
    if (!plan || !recovery || loading) return;

    setLoading(true);
    setError("");
    scrollToAnswer();
    let request;
    try {
      setMissionPhase("HUMAN APPROVAL");
      request = beginRequest(90000);
      const approval = await fetch(`${API_URL}/workspace/approve-recovery`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mission_id: plan.id, approved }),
        signal: request.signal,
      });
      const approvalData = await readJsonResponse(approval, "Recovery approval failed.");
      setMissionRecord(approvalData.mission);
      setAuditEvents(approvalData.mission.events || []);
      if (!approved) {
        setRecovery(approvalData.mission.recovery);
        setResult("Recovery was declined. The mission is blocked.");
        setMissionPhase("BLOCKED");
        return;
      }

      setRecovery(approvalData.mission.recovery);
      setMissionPhase("HUMAN APPROVAL");
      await new Promise((resolve) => setTimeout(resolve, 350));
      setStages((prev) => updateStage(prev, 3, "running"));
      const response = await fetch(
        `${API_URL}/mission/reexecute/${encodeURIComponent(plan.id)}`,
        { method: "POST", signal: request.signal }
      );
      await consumeMissionStream(response, { recoveryOnly: true });
      await refreshAudit(plan.id);
    } catch (err) {
      if (err.name === "AbortError" && !activeRequest.current) return;
      console.error(err);
      setError(err.message || "Recovery could not be executed.");
      setMissionPhase("INTERRUPTED");
      await refreshAudit(plan.id);
    } finally {
      request?.cleanup();
      setLoading(false);
    }
  }

  const canApplyChange = Boolean(
    plan?.contract?.requirement_specs?.length && CHANGEABLE_STATUSES.has(missionRecord?.status)
  );

  async function applyChange(text) {
    if (!plan || loading) return;

    setLoading(true);
    setError("");
    scrollToAnswer();
    setChangeLog((prev) => [...prev, { text, change: null }]);
    setGoal("");
    let request;
    try {
      request = beginRequest(90000);
      const response = await fetch(`${API_URL}/mission/${encodeURIComponent(plan.id)}/change`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        signal: request.signal,
      });
      setStages((prev) => updateStage(prev, 3, "running"));
      await consumeMissionStream(response, { recoveryOnly: true });
      await refreshAudit(plan.id);
    } catch (err) {
      if (err.name === "AbortError" && !activeRequest.current) return;
      console.error(err);
      setError(err.message || "The change could not be applied.");
      await refreshAudit(plan.id);
    } finally {
      request?.cleanup();
      setLoading(false);
    }
  }

  async function decideAmendment(optionId) {
    if (!plan || loading) return;

    setLoading(true);
    setError("");
    setAmendmentHidden(false);
    scrollToAnswer();
    let request;
    try {
      request = beginRequest(90000);
      const response = await fetch(`${API_URL}/mission/${encodeURIComponent(plan.id)}/amend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(optionId ? { option_id: optionId } : { reject: true }),
        signal: request.signal,
      });
      if (!optionId) {
        const data = await readJsonResponse(response, "The amendment decision failed.");
        setMissionRecord(data.mission);
        setRecovery(data.mission.recovery);
        setAuditEvents(data.mission.events || []);
        setResult("All amendment options were rejected. The mission is blocked.");
        setMissionPhase("BLOCKED");
        return;
      }
      setStages((prev) => updateStage(prev, 3, "running"));
      await consumeMissionStream(response, { recoveryOnly: true });
      await refreshAudit(plan.id);
    } catch (err) {
      if (err.name === "AbortError" && !activeRequest.current) return;
      console.error(err);
      setError(err.message || "The amendment could not be applied.");
      await refreshAudit(plan.id);
    } finally {
      request?.cleanup();
      setLoading(false);
    }
  }

  const amendmentPending = recovery?.kind === "amendment" && recovery?.status === "approval_required";

  function submitComposer() {
    const text = goal.trim();
    if (canApplyChange && CHANGE_WORDS.test(text)) applyChange(text);
    else generatePlan();
  }

  function resetExecution() {
    activeRequest.current?.abort(new DOMException("Mission was cancelled.", "AbortError"));
    activeRequest.current = null;
    setActiveView("mission");
    setGoal("");
    setSubmittedGoal("");
    setLoading(false);
    setPlan(null);
    setMissionRecord(null);
    setEvidenceRecords([]);
    setFinalSolution("");
    setSolutionMode("");
    setError("");
    setExecutionResults([]);
    setVerification(null);
    setRecovery(null);
    setApprovalRequired(false);
    setResult("");
    setChangeLog([]);
    setChatReplies([]);
    setPendingInput("");
    setTaskLive({});
    setLiveEvents([]);
    setStages(defaultStages.map((s) => ({ ...s, status: "idle" })));
    setMissionPhase("IDLE");
  }

  async function downloadReceipt() {
    const missionId = missionRecord?.id || plan?.id;
    if (!missionId || receiptBusy) return;
    setReceiptBusy(true);
    try {
      const response = await fetch(`${API_URL}/mission/${encodeURIComponent(missionId)}/receipt`, { signal: AbortSignal.timeout(15000) });
      if (!response.ok) await readJsonResponse(response, "The receipt could not be exported.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `hades-receipt-${missionId}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      refreshAudit(missionId);
    } catch (err) {
      setError(err.message || "The receipt could not be exported.");
    } finally {
      setReceiptBusy(false);
    }
  }

  async function loadView(view) {
    setActiveView(view);
    if (view === "mission") return;
    setViewLoading(true);
    setViewError("");
    try {
      let response;
      if (view === "history") response = await fetch(`${API_URL}/mission/state-from-workspace`, { signal: AbortSignal.timeout(12000) });
      else if (view === "workspace") response = await fetch(`${API_URL}/workspace/scan`, { method: "POST", signal: AbortSignal.timeout(12000) });
      else response = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(8000) });
      const data = await readJsonResponse(response, `Could not load ${view}.`);
      setViewData(data);
      if (view === "settings") setApiStatus(data.status === "healthy" ? "ONLINE" : "OFFLINE");
    } catch (err) {
      if (err.name !== "AbortError") setApiStatus("OFFLINE");
      setViewError(err.name === "TimeoutError" ? "The backend did not respond in time. Try refresh again." : err.message || "The backend is unavailable.");
    } finally {
      setViewLoading(false);
    }
  }

  async function openMissionFromHistory(missionId) {
    setViewLoading(true);
    setViewError("");
    try {
      const response = await fetch(`${API_URL}/mission/${encodeURIComponent(missionId)}`, { signal: AbortSignal.timeout(10000) });
      const mission = await readJsonResponse(response, "Could not reopen the selected mission.");
      if (mission.status === "error") throw new Error(mission.message || "Mission was not found.");
      setPlan(mission);
      setMissionRecord(mission);
      setSubmittedGoal(mission.goal || "");
      setGoal(mission.goal || "");
      setFinalSolution(mission.artifacts?.at(-1) || "");
      setSolutionMode(mission.provider || "LOCAL");
      setVerification(mission.verification || null);
      setRecovery(mission.recovery || null);
      setEvidenceRecords(mission.evidence || []);
      setAuditEvents(mission.events || []);
      setTaskLive({});
      setLiveEvents([]);
      setChangeLog([]);
      setExecutionResults((mission.evidence || []).map((item, index) => ({ id: `${item.step}-${index}`, task: item.step, tool: item.tool, provider: item.provider, result: item.output || item.error || "", status: item.status })));
      setApprovalRequired(mission.status === "awaiting_approval");
      setResult(mission.status === "complete" ? "Mission completed successfully. Requirements passed verification." : mission.status === "blocked" ? "Mission is blocked because its requirements remain unmet." : "Mission loaded from history.");
      setMissionPhase(mission.status === "complete" ? "VERIFIED RESULT" : mission.status === "recovery_required" ? "RECOVERY REQUIRED" : mission.status === "blocked" ? "BLOCKED" : mission.status === "awaiting_approval" ? "APPROVAL" : mission.status === "interrupted" ? "INTERRUPTED" : "EXECUTING");
      setActiveView("mission");
    } catch (err) {
      setViewError(err.name === "TimeoutError" ? "The backend did not respond in time." : err.message || "Could not reopen the mission.");
    } finally {
      setViewLoading(false);
    }
  }

  const hasConversation = Boolean(
    plan || finalSolution || error || result || executionResults.length || loading || chatReplies.length || pendingInput
  );
  const hasMission = Boolean(plan || finalSolution || result);
  const typedMission = Boolean(plan?.contract?.requirement_specs?.length);
  const dockVisible = Boolean(plan && (approvalRequired || (recovery?.status === "approval_required" && !amendmentPending)));
  const selectView = (view) => {
    if (view === "mission") resetExecution();
    else loadView(view);
    setShowSidebar(false);
  };

  return (
    <div className={`hades-root font-sans antialiased text-white selection:bg-cyan-500/30 selection:text-cyan-200 ${composerHidden ? "composer-is-hidden" : ""}`}>
      {/* 3D ANIMATED WEBGL BACKGROUND */}
      <ThreeBackground subdued={hasConversation} />

      {/* MOBILE SIDEBAR DRAWER */}
      <AnimatePresence>
        {showSidebar && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowSidebar(false)}
              className="fixed inset-0 bg-black/70 backdrop-blur-md z-40 md:hidden"
            />
            <motion.div
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed inset-y-0 left-0 w-64 bg-[#080B12]/95 border-r border-white/10 z-50 md:hidden"
            >
              <Sidebar
                onNewMission={() => {
                  resetExecution();
                  setShowSidebar(false);
                }}
                onNavigate={selectView}
                activeView={activeView}
                onClose={() => setShowSidebar(false)}
                isMobile
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* DESKTOP SIDEBAR */}
      <aside className="hidden md:block fixed inset-y-0 left-0 w-64 z-30 border-r border-white/[0.08] bg-[#080B12]/80 backdrop-blur-xl">
        <Sidebar onNewMission={resetExecution} onNavigate={selectView} activeView={activeView} />
      </aside>

      {/* MAIN VIEWPORT */}
      <div className="md:pl-64 flex flex-col min-h-screen relative z-10">
        <TopBar
          onOpenSidebar={() => setShowSidebar(true)}
          activeMissionGoal={submittedGoal || goal}
          apiStatus={apiStatus}
        />

        {/* CONVERSATION VIEWPORT */}
        <main
          className={`flex-1 w-full ${activeView === "mission" && hasConversation ? "max-w-7xl" : "max-w-4xl"} mx-auto px-4 sm:px-6 pt-6`}
          style={{ paddingBottom: `calc(var(--composer-h, 9rem) + ${dockVisible ? "5.5rem" : "0px"} + 1.5rem)` }}
        >
          {activeView === "history" && <MissionHistoryPage missions={viewData?.missions || []} loading={viewLoading} error={viewError} onRefresh={() => loadView("history")} onSelect={openMissionFromHistory} />}
          {activeView === "workspace" && <WorkspacePage snapshot={viewData?.snapshot} loading={viewLoading} error={viewError} onRefresh={() => loadView("workspace")} />}
          {activeView === "settings" && <SettingsPage health={viewData} loading={viewLoading} error={viewError} onRefresh={() => loadView("settings")} />}

          {activeView === "mission" && !hasConversation && (
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="welcome-hero-container text-center my-auto py-12 flex flex-col items-center"
            >
              <div className="hero-orb-wrapper">
                <Sparkles size={28} className="text-cyan-300" />
                <div className="hero-orb-ring" />
              </div>

              <div className="hero-eyebrow font-mono">
                HUMAN-AI DRIVEN EXECUTION SYSTEM
              </div>

              <h1 className="hero-heading">
                Don't just ask AI.
                <br />
                <span className="hero-gradient-text">Give it a goal.</span>
              </h1>

              <p className="hero-subtext">
                HADES is an autonomous execution agent. Give it a goal, HADES builds
                an execution plan, requests approval, executes tasks with tools,
                verifies results, and delivers the answer.
              </p>

              <button type="button" className="guided-demo-button" onClick={() => generatePlan({ demoMode: true })} disabled={loading}>
                <Sparkles size={16} />
                <span><strong>Run the guided demo</strong><small>Local-only · includes a labeled failure and approved recovery</small></span>
              </button>

              <div className="hero-examples-label font-mono">or start from an example</div>

              <div className="hero-suggestions-grid">
                <button
                  onClick={() => setGoal(TRIP_GOAL)}
                  className="suggestion-chip suggestion-chip-primary"
                >
                  <Plane size={15} className="text-emerald-300 shrink-0" />
                  <span>Plan my Bengaluru trip (weather, packing, calendar, leave email, ₹4,000 budget)</span>
                </button>

                <button
                  onClick={() => {
                    setGoal(
                      "Prepare my Smart Energy Meter project for tomorrow's hackathon presentation."
                    );
                  }}
                  className="suggestion-chip"
                >
                  <Zap size={15} className="text-amber-400 shrink-0" />
                  <span>Prepare my Smart Energy Meter project</span>
                </button>

                <button
                  onClick={() => {
                    setGoal(
                      "Research the latest advances in electric vehicle battery technology and summarize the key findings."
                    );
                  }}
                  className="suggestion-chip"
                >
                  <Sparkles size={15} className="text-cyan-400 shrink-0" />
                  <span>Research EV battery technology</span>
                </button>

                <button
                  onClick={() => {
                    setGoal(
                      "Analyze project requirements and generate a step-by-step technical implementation roadmap."
                    );
                  }}
                  className="suggestion-chip"
                >
                  <FileText size={15} className="text-violet-400 shrink-0" />
                  <span>Generate implementation roadmap</span>
                </button>
              </div>
            </motion.div>
          )}

          {/* ── CHAT: question, then the answer, right at the top ── */}
          {activeView === "mission" && hasConversation && (
            <div className="chat-column space-y-5">
              {hasMission && submittedGoal && <UserMessage text={submittedGoal} />}

              {hasMission && <AssistantMessage>
                <AnswerCard
                  loading={loading && !pendingInput}
                  phase={missionPhase}
                  plan={plan}
                  approvalRequired={approvalRequired}
                  finalSolution={finalSolution}
                  solutionMode={solutionMode}
                  verification={verification}
                  recovery={recovery}
                  result={result}
                  lastActivity={liveEvents.at(-1)?.message}
                  onShowEvidence={scrollToEvidence}
                  onDownloadReceipt={plan ? downloadReceipt : undefined}
                  receiptBusy={receiptBusy}
                />
              </AssistantMessage>}

              {/* Follow-up changes sent from chat */}
              {changeLog.map((entry, index) => (
                <div key={`change-${index}`} className="space-y-5">
                  <UserMessage text={entry.text} />
                  {entry.change && (
                    <AssistantMessage>
                      <div className="error-glass-box change-glass-box">
                        <AlertTriangle size={18} className="text-amber-300 shrink-0" />
                        <div className="min-w-0">
                          <div className="font-mono text-xs font-bold text-amber-200">CONTRACT CHANGED · {entry.change.message?.toUpperCase()}</div>
                          <p className="text-xs text-white/75 mt-1">{describeDiff(entry.change.diff)}</p>
                          <p className="text-xs text-amber-200/80 mt-1">
                            Stale: {(entry.change.stale_evidence || []).map((item) => `${item.step} (${item.id})`).join(", ") || "none"}
                          </p>
                          <p className="text-xs text-white/55 mt-1">
                            Still valid: {(entry.change.unaffected_steps || []).join(", ") || "none"}
                          </p>
                          <p className="text-xs text-white/55 mt-1">The answer above has been updated.</p>
                        </div>
                      </div>
                    </AssistantMessage>
                  )}
                </div>
              ))}

              {/* Questions and chat: answered, never turned into missions */}
              {chatReplies.map((entry, index) => (
                <div key={`reply-${index}`} className="space-y-5">
                  <UserMessage text={entry.text} />
                  <AssistantMessage>
                    <NotAGoalCard reply={entry.reply} disabled={loading} onExample={(text) => generatePlan({ goalText: text })} />
                  </AssistantMessage>
                </div>
              ))}

              {pendingInput && (
                <div className="space-y-5">
                  <UserMessage text={pendingInput} />
                  <AssistantMessage>
                    <p className="answer-thinking">Reading your message…</p>
                  </AssistantMessage>
                </div>
              )}

              <AnimatePresence>
                {error && (
                  <AssistantMessage>
                    <div className="error-glass-box">
                      <AlertTriangle size={18} className="text-rose-400 shrink-0" />
                      <div>
                        <div className="font-mono text-xs font-bold text-rose-300">
                          EXECUTION INTERRUPTED
                        </div>
                        <p className="text-xs text-rose-200/80 mt-0.5">{error}</p>
                      </div>
                    </div>
                  </AssistantMessage>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* ── EVIDENCE: everything that proves the answer, below the fold ── */}
          {activeView === "mission" && hasConversation && missionPhase !== "IDLE" && (
            <section id="mission-evidence" className="evidence-section">
              <div className="evidence-divider">
                <span>Evidence &amp; how HADES verified this</span>
              </div>

              <MissionProgress phase={missionPhase} recoveryUsed={Boolean(missionRecord?.demo_mode || missionRecord?.recovery_attempts || recovery)} />

              {/* CONTRACT · DEPENDENCIES · EVENT STREAM */}
              {typedMission && (
                <MissionBoard
                  mission={missionRecord?.id === plan.id ? missionRecord : plan}
                  verification={verification}
                  evidence={evidenceRecords}
                  taskLive={taskLive}
                  auditEvents={auditEvents}
                  liveEvents={liveEvents}
                  onDownloadReceipt={downloadReceipt}
                  receiptBusy={receiptBusy}
                />
              )}

              <div className="evidence-column space-y-5">
                {plan && (
                  <ExecutionPlan
                    plan={plan}
                    isLocal={isLocalPlan}
                    approvalRequired={false}
                    loading={loading}
                  />
                )}

                <ExecutionStatus stages={stages} isExecuting={loading} phase={missionPhase} />

                {result && (
                  <div className={`mission-outcome ${missionPhase === "VERIFIED RESULT" ? "outcome-success" : missionPhase === "BLOCKED" || missionPhase === "INTERRUPTED" ? "outcome-error" : "outcome-pending"}`} role="status">
                    <strong>{missionPhase}</strong>
                    <p>{result}</p>
                  </div>
                )}

                {recovery && (
                  <div className="error-glass-box recovery-glass-box">
                    <AlertTriangle size={18} className="text-amber-300 shrink-0" />
                    <div className="min-w-0">
                      <div className="font-mono text-xs font-bold text-amber-200">
                        {recovery.status === "blocked" || recovery.status === "rejected" ? "RECOVERY BLOCKED" : recovery.status === "resolved" ? "RECOVERY VERIFIED" : recovery.status === "amended" ? "AMENDMENT APPLIED · RE-VERIFYING" : recovery.kind === "amendment" ? "CONTRACT AMENDMENT REQUIRED" : "RECOVERY REQUIRED"}
                      </div>
                      <p className="text-xs text-white/75 mt-1">
                        Missing: {(recovery.missing_requirements || []).join("; ") || recovery.reason}
                      </p>
                      <p className="text-xs text-white/60 mt-1">
                        Affected tasks: {(recovery.affected_tasks || []).join(", ") || "verification"}
                      </p>
                      {(recovery.actions || []).map((action) => (
                        <p key={action} className="text-xs text-white/60 mt-1">• {action}</p>
                      ))}
                      {recovery.attempts != null && (
                        <p className="text-[11px] text-white/45 mt-2">
                          Recovery attempts: {recovery.attempts}/{recovery.plan?.max_attempts ?? 1}
                        </p>
                      )}
                      {amendmentPending && amendmentHidden && (
                        <button type="button" className="amendment-reopen" onClick={() => setAmendmentHidden(false)}>
                          Review amendment options
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {executionResults.length > 0 && <ToolDetails executionResults={executionResults} />}

                {evidenceRecords.length > 0 && <EvidencePanel evidence={evidenceRecords} />}

                {/* Typed missions show verification and the audit stream on the board. */}
                {verification && !typedMission && <VerificationPanel verification={verification} />}

                {auditEvents.length > 0 && !typedMission && (
                  <details className="w-full rounded-xl border border-white/10 bg-black/20 p-4">
                    <summary className="cursor-pointer text-xs font-mono font-bold tracking-wider text-cyan-200">
                      MISSION AUDIT TIMELINE ({auditEvents.length})
                    </summary>
                    <ol className="mt-3 space-y-2">
                      {auditEvents.map((entry) => (
                        <li key={`${entry.sequence}-${entry.kind}`} className="border-l border-cyan-400/30 pl-3">
                          <div className="flex flex-wrap gap-x-2 text-[11px]">
                            <span className="text-cyan-200">{entry.kind}</span>
                            <time className="text-white/40">{entry.time ? new Date(entry.time).toLocaleTimeString() : ""}</time>
                          </div>
                          <p className="text-xs text-white/70">{entry.message}</p>
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
              </div>
            </section>
          )}
        </main>

        {/* STICKY APPROVAL DOCK FLOATING ABOVE COMPOSER */}
        <AnimatePresence>
          {approvalRequired && plan && (
            <ApprovalControl
              title="MISSION APPROVAL"
              approveLabel="Approve & Execute"
              onApprove={approveAndExecute}
              onReset={resetExecution}
              isLocal={isLocalPlan}
              loading={loading}
              description={typedMission
                ? "Reads the forecast from Open-Meteo (read-only). Every other tool writes local files. Nothing is sent."
                : plan.approval?.reason || (plan.approval?.risk === "HIGH" ? "High-impact mission. Human approval is required." : undefined)}
            />
          )}
          {recovery?.status === "approval_required" && !amendmentPending && plan && (
            <ApprovalControl
              title="RECOVERY APPROVAL"
              approveLabel="Approve Recovery"
              cancelLabel="Block Mission"
              description="Recovery will rerun only the affected tasks, then verify the requirements again."
              onApprove={() => approveRecoveryAndExecute(true)}
              onReset={() => approveRecoveryAndExecute(false)}
              isLocal
              loading={loading}
            />
          )}
        </AnimatePresence>

        {amendmentPending && !amendmentHidden && plan && (
          <AmendmentModal
            recovery={recovery}
            loading={loading}
            onChoose={decideAmendment}
            onReject={() => decideAmendment(null)}
            onClose={() => setAmendmentHidden(true)}
          />
        )}

        {/* COMPOSER FIXED AT BOTTOM */}
        <footer ref={footerRef} className={`composer-footer fixed bottom-0 left-0 md:left-64 right-0 z-20 px-4 pb-4 pt-2 pointer-events-none ${composerHidden ? "is-hidden" : ""}`}>
          <div className="max-w-3xl mx-auto pointer-events-auto">
            <ChatComposer
              goal={goal}
              setGoal={setGoal}
              onSubmit={submitComposer}
              placeholder={canApplyChange ? "Describe a change (e.g. “moved to Wednesday”), or start a new mission" : undefined}
              loading={loading}
              hasActiveMission={hasConversation}
              onReset={resetExecution}
            />
          </div>
        </footer>
      </div>
    </div>
  );
}
