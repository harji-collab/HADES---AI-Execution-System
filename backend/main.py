import asyncio
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import goal_compiler
import trip_tools
import exam_tools  # registers the exam domain's tasks and tools
import verifiers
import amendments

from google import genai
from google.genai import types

try:
    from groq import Groq
except ImportError:
    Groq = None


# ============================================================
# HADES CORE
# ============================================================

load_dotenv()

APP_VERSION = "3.5.0"

ROOT = Path(
    os.getenv(
        "HADES_WORKSPACE",
        Path(__file__).resolve().parent.parent,
    )
).resolve()

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]
AI_REQUEST_TIMEOUT_MS = 8000
AI_REQUEST_TIMEOUT_SECONDS = AI_REQUEST_TIMEOUT_MS / 1000
MAX_RECOVERY_ATTEMPTS = 1
MAX_AMENDMENTS = 3

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

MISSIONS = {}

IGNORE = {
    ".git",
    "node_modules",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
}

_gemini_blocked_until = 0
_groq_client = None


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="HADES",
    description="Human-AI Driven Execution System",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class Goal(BaseModel):
    goal: str


class Approved(BaseModel):
    goal: str
    plan: dict
    approved: bool = False


class Change(BaseModel):
    mission_id: str
    reason: str = "Mission input changed."


class Recovery(BaseModel):
    mission_id: str
    approved: bool


# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def event(name, data):
    return (
        f"event: {name}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def clip(value, limit=10000):
    return str(value or "")[:limit]


def ai_enhancements_enabled():
    return os.getenv(
        "HADES_AI_ENHANCEMENTS",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}


def parse_json(text):
    if not text:
        return None

    text = str(text).strip()

    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
        flags=re.I,
    )

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(
        r"\{.*\}",
        text,
        flags=re.S,
    )

    if match:
        try:
            return json.loads(match.group())
        except Exception:
            return None

    return None


# ============================================================
# GEMINI
# ============================================================

def gemini(prompt, grounded=False, on_request=None):

    global _gemini_blocked_until

    key = os.getenv("GEMINI_API_KEY")

    if not key:
        return None, "LOCAL"

    if time.time() < _gemini_blocked_until:
        return None, "LOCAL"

    try:
        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                timeout=AI_REQUEST_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(
                    attempts=1
                ),
            ),
        )
    except Exception as exc:
        print("[Gemini Init]", exc)
        return None, "LOCAL"

    # One request per provider keeps failure latency bounded. Planning never
    # reaches this function; this is only an optional execution enhancement.
    for model in GEMINI_MODELS[:1]:

        try:

            if grounded:
                config = types.GenerateContentConfig(
                    temperature=0.2,
                    tools=[
                        types.Tool(
                            google_search=types.GoogleSearch()
                        )
                    ],
                )
            else:
                config = types.GenerateContentConfig(
                    temperature=0.2
                )

            if on_request:
                on_request("GEMINI")

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

            text = getattr(
                response,
                "text",
                None,
            )

            if text:
                print(
                    f"[Gemini] {model} OK"
                )
                return text.strip(), "GEMINI"

        except Exception as exc:

            message = str(exc)

            print(
                f"[Gemini] {model}: {message}"
            )

            lowered = message.lower()

            if (
                "429" in message
                or "resource_exhausted" in lowered
                or "quota" in lowered
                or "rate limit" in lowered
            ):
                _gemini_blocked_until = (
                    time.time() + 300
                )

                print(
                    "[Gemini] Quota exhausted. "
                    "Switching to Groq."
                )

                break

    return None, "LOCAL"


# ============================================================
# GROQ
# ============================================================

def groq_client():

    global _groq_client

    key = os.getenv(
        "GROQ_API_KEY"
    )

    if not key:
        print(
            "[Groq] GROQ_API_KEY missing."
        )
        return None

    if Groq is None:
        print(
            "[Groq] SDK missing."
            " Run: pip install -U groq"
        )
        return None

    if _groq_client is None:

        try:
            _groq_client = Groq(
                api_key=key,
                timeout=AI_REQUEST_TIMEOUT_SECONDS,
                max_retries=0,
            )

            print(
                "[Groq] Client initialized."
            )

        except Exception as exc:
            print(
                "[Groq Init]",
                exc,
            )
            return None

    return _groq_client


def groq(
    prompt,
    purpose="general",
    search=False,
    json_mode=False,
    on_request=None,
):

    client = groq_client()

    if client is None:
        return None, "LOCAL"

    budgets = {
        "compiler": 700,
        "research": 1800,
        "content": 1800,
        "verification": 700,
        "recovery": 900,
        "general": 900,
    }

    max_tokens = budgets.get(
        purpose,
        900,
    )

    for model in GROQ_MODELS[:1]:

        try:

            request = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are HADES secondary "
                            "intelligence. "
                            "Be precise, factual and "
                            "execution-focused. "
                            "Never fabricate evidence."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0.2,
                "max_completion_tokens": max_tokens,
                "reasoning_effort": "low",
                "stream": False,
            }

            if search:
                request["tools"] = [
                    {
                        "type": "browser_search"
                    }
                ]

                request["tool_choice"] = "required"

            if json_mode and not search:
                request["response_format"] = {
                    "type": "json_object"
                }

            print(
                f"[Groq] {model} "
                f"purpose={purpose} "
                f"search={search}"
            )

            if on_request:
                on_request("GROQ")

            response = (
                client.chat.completions.create(
                    **request
                )
            )

            if not response.choices:
                continue

            content = (
                response
                .choices[0]
                .message
                .content
                or ""
            )

            if content.strip():

                print(
                    f"[Groq] {model} OK"
                )

                return (
                    content.strip(),
                    "GROQ",
                )

        except Exception as exc:

            status = getattr(
                exc,
                "status_code",
                None,
            )

            print(
                f"[Groq] {model} "
                f"HTTP {status or 'ERROR'}: "
                f"{exc}"
            )

    print(
        "[Groq] All configured models failed."
    )

    return None, "LOCAL"


# ============================================================
# UNIFIED AI ROUTER
# ============================================================

# Mission phases are counted per mission. "conversation" covers classifying
# non-goal input and its quick answer: no mission exists, so it is only
# counted globally and never mixed into a mission's receipt.
MISSION_LLM_PHASES = ("planning", "execution", "recovery", "verification")
LLM_PHASES = MISSION_LLM_PHASES + ("conversation",)
LLM_CALLS = {phase: 0 for phase in LLM_PHASES}
_llm_lock = threading.Lock()


def new_llm_counter():
    return {phase: 0 for phase in MISSION_LLM_PHASES}


def llm_call(
    prompt,
    phase,
    counter=None,
    purpose="general",
    grounded=False,
    json_mode=False,
):
    """The only path to an LLM. Counts every provider request by mission
    phase, globally and in the mission's own counter. Verification is
    deterministic by design, so verification-phase calls are refused."""
    if phase not in LLM_PHASES:
        raise ValueError(f"Unknown LLM phase {phase!r}.")
    if phase == "verification":
        raise RuntimeError("Verification must not call an LLM.")

    def on_request(provider):
        with _llm_lock:
            LLM_CALLS[phase] += 1
            if counter is not None:
                counter[phase] = counter.get(phase, 0) + 1

    return ai(prompt, purpose=purpose, grounded=grounded, json_mode=json_mode, on_request=on_request)


def ai(
    prompt,
    purpose="general",
    grounded=False,
    json_mode=False,
    on_request=None,
):

    result, provider = gemini(
        prompt,
        grounded=grounded,
        on_request=on_request,
    )

    if result:
        return result, provider

    result, provider = groq(
        prompt,
        purpose=purpose,
        search=grounded,
        json_mode=json_mode,
        on_request=on_request,
    )

    if result:
        return result, provider

    return None, "LOCAL"


# ============================================================
# WORKSPACE
# ============================================================

def scan_workspace():

    files = []
    max_files = 1000
    max_directories = 2000
    visited_directories = 0

    # Prune dependency/build folders before descending, and cap the number of
    # files hashed so a large workspace cannot make planning unbounded.
    for current, directories, filenames in os.walk(ROOT):
        visited_directories += 1
        if visited_directories > max_directories:
            break

        directories[:] = [
            name for name in directories
            if name not in IGNORE and not name.startswith(".")
        ]

        for filename in filenames:
            if len(files) >= max_files:
                break

            if (
                filename.startswith(".env")
                or filename.endswith((".pem", ".key"))
            ):
                continue

            path = Path(current) / filename
            try:
                size = path.stat().st_size
                if size > 250000:
                    continue
                files.append({
                    "path": str(path.relative_to(ROOT)),
                    "size": size,
                    "sha": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                })
            except (OSError, ValueError):
                continue

        if len(files) >= max_files:
            break

    return {
        "root": str(ROOT),
        "files": files,
    }


def workspace_delta(
    old,
    new,
):

    old_files = {
        item["path"]: item["sha"]
        for item in old.get(
            "files",
            [],
        )
    }

    new_files = {
        item["path"]: item["sha"]
        for item in new.get(
            "files",
            [],
        )
    }

    return {
        "added": [
            path
            for path in new_files
            if path not in old_files
        ],
        "removed": [
            path
            for path in old_files
            if path not in new_files
        ],
        "changed": [
            path
            for path in new_files
            if (
                path in old_files
                and old_files[path]
                != new_files[path]
            )
        ],
    }


# ============================================================
# GOAL COMPILER
# ============================================================

def fallback_contract(goal):

    lowered = goal.lower()

    needs_web = any(
        word in lowered
        for word in [
            "research",
            "latest",
            "current",
            "compare",
            "technology",
            "market",
            "source",
            "news",
            "price",
            "pricing",
        ]
    )

    needs_workspace = any(
        word in lowered
        for word in [
            "code",
            "project",
            "repo",
            "workspace",
            "files",
            "app",
            "website",
        ]
    )

    requirements = [
        item.strip(" \t-*\r")
        for item in re.split(
            r"(?:\n+|;\s*|(?<=[.!?])\s+)",
            goal,
        )
        if item.strip(" \t-*\r")
    ]

    if not requirements:
        requirements = [goal]

    return {
        "objective": goal,
        "requirements": requirements,
        "constraints": [
            "Do not fabricate evidence"
        ],
        "deliverables": [
            "Usable final result"
        ],
        "success_criteria": [
            "Core requirements are satisfied",
            "Critical claims are supported",
        ],
        "needs_web": needs_web,
        "needs_workspace": needs_workspace,
        "risk_level": "LOW",
    }


def typed_contract(goal, decomposition, compiler):

    facts = decomposition["facts"]
    specs = decomposition["requirements"]
    domain = decomposition.get("domain") or "trip"
    constraints = ["Do not fabricate evidence"]
    if facts.get("max_budget") is not None and any(spec["type"] == "budget" for spec in specs):
        constraints.append(f"Total trip cost must not exceed ₹{facts['max_budget']:,}")

    if domain == "exam":
        parameters = {key: facts.get(key) for key in ("subject", "exam_date")}
        assumptions = [
            f"Up to {exam_tools.MAX_SESSIONS} sessions on the days before the exam (evenings on weekdays, mornings on weekends).",
            "Topics come from a local syllabus fixture.",
        ]
        constraints.append("Every study session must end before the exam date and sessions must not overlap")
    else:
        parameters = {
            **{key: facts.get(key) for key in ("destination", "trip_date", "max_budget", "currency", "recipient")},
            "travel_mode": "train",
        }
        assumptions = [
            "Travel mode defaults to train.",
            f"Fares come from a local fixture (origin: {trip_tools.load_fixture('fares.json')['origin']}).",
        ]

    return {
        "objective": goal,
        "domain": domain,
        # Human-readable descriptions, kept as strings for existing consumers.
        "requirements": [spec["description"] for spec in specs],
        "requirement_specs": specs,
        "parameters": parameters,
        "assumptions": assumptions,
        "constraints": constraints,
        "deliverables": [spec["description"] for spec in specs],
        "success_criteria": [
            "Every requirement passes its named verifier",
        ],
        "needs_web": False,
        "needs_workspace": False,
        "risk_level": "LOW",
        "compiler": compiler,
    }


def compile_goal(goal, counter=None):

    # The rule-based path is local and deterministic. An LLM may propose a
    # decomposition only when enhancements are enabled, and its proposal is
    # used only after validation against the requirement type registry and
    # the facts stated in the goal.
    decomposition = goal_compiler.decompose_goal(goal)
    provider = "LOCAL"
    compiler = {"method": "rules", "llm_rejected": None}

    if ai_enhancements_enabled():
        text, llm_provider = llm_call(
            goal_compiler.llm_prompt(goal),
            "planning",
            counter,
            purpose="compiler",
            json_mode=True,
        )
        if text:
            try:
                decomposition = goal_compiler.validate_decomposition(
                    parse_json(text),
                    goal,
                    decomposition,
                )
                provider = llm_provider
                compiler = {"method": "llm", "llm_rejected": None}
            except ValueError as exc:
                compiler["llm_rejected"] = str(exc)
                print("[Compiler] LLM proposal rejected:", exc)

    if decomposition is None:
        contract = fallback_contract(goal)
        contract["compiler"] = {**compiler, "method": "legacy"}
        return contract, "LOCAL"

    unregistered = [
        spec["tool"] for spec in decomposition["requirements"]
        if spec["tool"] not in TOOL_POLICY
    ]
    if unregistered:
        raise RuntimeError(f"Requirement tools missing from the registry: {unregistered}")

    return typed_contract(goal, decomposition, compiler), provider


# ============================================================
# MISSION GRAPH
# ============================================================

def build_steps(contract):

    if contract.get("requirement_specs"):
        return trip_tools.build_trip_steps(contract)

    steps = [
        {
            "id": "understand",
            "title": "Understand goal",
            "tool": "mission",
            "depends_on": [],
        },
        {
            "id": "workspace",
            "title": "Inspect workspace",
            "tool": "workspace",
            "depends_on": [
                "understand"
            ],
        },
        {
            "id": "research",
            "title": "Research evidence",
            "tool": "research",
            "depends_on": [
                "understand"
            ],
        },
        {
            "id": "execute",
            "title": "Build deliverable",
            "tool": "content",
            "depends_on": [
                "understand",
                "workspace",
                "research",
            ],
        },
        {
            "id": "verify",
            "title": "Verify mission",
            "tool": "verification",
            "depends_on": [
                "execute"
            ],
        },
    ]

    if not contract.get(
        "needs_workspace"
    ):
        steps = [
            step
            for step in steps
            if step["tool"]
            != "workspace"
        ]

    if not contract.get(
        "needs_web"
    ):
        steps = [
            step
            for step in steps
            if step["tool"]
            != "research"
        ]

    valid_ids = {
        step["id"]
        for step in steps
    }

    for step in steps:
        step["depends_on"] = [
            dep
            for dep in step["depends_on"]
            if dep in valid_ids
        ]

    return steps


TOOL_POLICY = {
    "mission": {"name": "Mission Compiler", "risk": "LOW", "permissions": ["read:mission"]},
    "workspace": {"name": "Workspace Scanner", "risk": "LOW", "permissions": ["read:workspace"]},
    "research": {"name": "Browser Research", "risk": "LOW", "permissions": ["network:read"]},
    "content": {"name": "Deliverable Synthesizer", "risk": "LOW", "permissions": ["write:mission-artifact"]},
    "verification": {"name": "Verification Engine", "risk": "LOW", "permissions": ["read:evidence"]},
    "destination": {"name": "Destination Resolver", "risk": "LOW", "permissions": ["read:local-gazetteer"]},
    "weather": {"name": "Open-Meteo Weather", "risk": "LOW", "permissions": ["network:read:api.open-meteo.com", "write:weather-cache"]},
    "packing_base": {"name": "Packing Essentials", "risk": "LOW", "permissions": ["read:mission"]},
    "packing_list": {"name": "Packing List Builder", "risk": "LOW", "permissions": ["read:evidence"]},
    "calendar": {"name": "Calendar File Writer", "risk": "LOW", "permissions": ["write:outputs"]},
    "email_template": {"name": "Leave Template Loader", "risk": "LOW", "permissions": ["read:fixtures"]},
    "leave_email": {"name": "Leave Email Drafter", "risk": "LOW", "permissions": ["write:outputs"]},
    "fares": {"name": "Fare Lookup", "risk": "LOW", "permissions": ["read:fixtures"]},
    "budget": {"name": "Budget Calculator", "risk": "LOW", "permissions": ["read:evidence"]},
    "syllabus": {"name": "Syllabus Loader", "risk": "LOW", "permissions": ["read:fixtures"]},
    "study_planner": {"name": "Study Session Planner", "risk": "LOW", "permissions": ["read:evidence"]},
    "study_calendar": {"name": "Study Calendar Writer", "risk": "LOW", "permissions": ["write:outputs"]},
    "revision_checklist": {"name": "Revision Checklist Builder", "risk": "LOW", "permissions": ["write:outputs"]},
}


def latest_evidence(mission):
    """Latest evidence record per task id."""
    latest = {}
    for item in mission.get("evidence", []):
        latest[item.get("step")] = item
    return latest


def route_tool(step, mission):
    """Resolve a planned task against the local tool registry and policy."""
    tool = step.get("tool")
    policy = TOOL_POLICY.get(tool)
    if not policy:
        raise ValueError(f"No registered tool for task {step.get('id')!r}.")
    parameters = mission["contract"].get("parameters", {})
    return {
        "tool": tool,
        "inputs": {
            "goal": mission["goal"],
            "task_id": step["id"],
            "requirements": mission["contract"].get("requirements", []),
            **({"workspace_paths": [item.get("path") for item in mission.get("workspace", {}).get("files", [])]} if tool in {"workspace", "content"} else {}),
            # Contract parameters this task reads; a change to any of them
            # makes this task's evidence stale.
            **({"parameters": {key: parameters.get(key) for key in step["reads"]}} if step.get("reads") else {}),
        },
        "permissions": list(policy["permissions"]),
        "risk": policy["risk"],
    }


# ============================================================
# MISSION
# ============================================================

def create_mission(goal):

    llm_calls = new_llm_counter()
    contract, provider = compile_goal(
        goal,
        llm_calls,
    )

    workspace = (
        scan_workspace()
        if contract.get("needs_workspace")
        else {"root": str(ROOT), "files": []}
    )

    mission_id = hashlib.sha1(
        f"{goal}{time.time()}".encode()
    ).hexdigest()[:12]

    mission = {
        "id": mission_id,
        "goal": goal,
        "status": "awaiting_approval",
        "provider": provider,
        "created_at": now(),
        "contract": contract,
        "steps": build_steps(
            contract
        ),
        "workspace": workspace,
        "evidence": [],
        "artifacts": [],
        "verification": None,
        "recovery": None,
        "recovery_attempts": 0,
        "change": None,
        "events": [],
        "tool_runs": [],
        "approval": {"required": True, "status": "pending", "risk": "LOW"},
        "llm_calls": llm_calls,
    }

    high_impact = re.search(r"\b(delete|remove|transfer|payment|pay|purchase|buy|send|publish|deploy|grant access|change password)\b", goal, re.I)
    mission["approval"] = {
        "required": True,
        "status": "pending",
        "risk": "HIGH" if high_impact else "LOW",
        "reason": "High-impact action requires explicit human approval." if high_impact else "Human approval required before execution.",
    }

    MISSIONS[
        mission_id
    ] = mission
    log(mission, "mission_created", "Local mission plan created.", {
        "requirements": contract.get("requirements", []),
        "requirement_specs": [
            {"id": spec["id"], "type": spec["type"], "verifier": spec["verifier"], "depends_on": spec["depends_on"]}
            for spec in contract.get("requirement_specs", [])
        ],
        "compiler": contract.get("compiler"),
        "steps": [step.get("id") for step in mission["steps"]],
    })

    return mission


def log(
    mission,
    kind,
    message,
    metadata=None,
):

    events = mission.setdefault("events", [])
    entry = {
        "time": now(),
        "sequence": len(events) + 1,
        "mission_id": mission.get("id"),
        "kind": kind,
        "message": message,
        # Snapshot: callers often pass live mission dicts that change later,
        # which would silently break the event's hash.
        "metadata": json.loads(json.dumps(metadata or {}, ensure_ascii=False, default=str)),
        "prev_hash": events[-1]["hash"] if events and events[-1].get("hash") else GENESIS_HASH,
    }
    entry["hash"] = event_hash(entry)
    events.append(entry)


GENESIS_HASH = "0" * 64


def event_hash(entry):
    """SHA-256 over the canonical JSON of an event without its own hash."""
    body = {key: value for key, value in entry.items() if key != "hash"}
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_event_chain(events):
    """Recompute every hash and link. Returns (valid, first_bad_sequence)."""
    previous = GENESIS_HASH
    for entry in events:
        if entry.get("prev_hash") != previous or entry.get("hash") != event_hash(entry):
            return False, entry.get("sequence")
        previous = entry["hash"]
    return True, None


# ============================================================
# RESEARCH
# ============================================================

def research(goal, phase="execution", counter=None):

    prompt = f"""
You are the HADES Research Agent.

Use real-time browser search.

Research this goal:

{goal}

Return a compact evidence brief.

For every important factual claim:
- identify the source
- include the source title
- include publication date when available
- include the relevant factual finding
- clearly distinguish facts from uncertainty

Prioritize:
- primary sources
- official technical documentation
- academic papers
- reputable industry sources

Do NOT invent citations.

If a fact cannot be verified, explicitly say:
NOT VERIFIED.

Do not provide hidden reasoning.
"""

    result, provider = llm_call(
        prompt,
        phase,
        counter,
        purpose="research",
        grounded=True,
    )

    if result:
        return result, provider

    return (
        "RESEARCH BLOCKED\n\n"
        "HADES could not access a live research "
        "provider during this execution.\n"
        "No external evidence was fabricated.",
        "LOCAL",
    )


# ============================================================
# CONTENT
# ============================================================

def synthesize(
    goal,
    contract,
    evidence,
    allow_ai=True,
    phase="execution",
    counter=None,
):

    evidence_text = clip(
        "\n\n".join(evidence),
        16000,
    )

    prompt = f"""
You are the HADES Deliverable Agent.

Produce the requested final deliverable.

GOAL:
{goal}

MISSION CONTRACT:
{json.dumps(
    contract,
    ensure_ascii=False,
)}

AVAILABLE EVIDENCE:
{evidence_text}

Rules:

- Satisfy the mission requirements.
- Use only supported information.
- Preserve source attribution where relevant.
- Never invent measurements, statistics or citations.
- Clearly mark unsupported information.
- Do not expose chain-of-thought.

Produce a useful final answer.
"""

    if allow_ai and ai_enhancements_enabled():
        result, provider = llm_call(
            prompt,
            phase,
            counter,
            purpose="content",
        )

        if result:
            return result, provider

    lowered = goal.casefold()
    if re.search(r"\b(checklist|to-do list|todo list)\b", lowered):
        count_match = re.search(
            r"\b(\d{1,2})\s*(?:-\s*)?(?:point|item|step)s?\b",
            lowered,
        )
        count = min(10, max(1, int(count_match.group(1)))) if count_match else 3
        checklist = [
            "Confirm the demo setup and materials",
            "Rehearse the main walkthrough",
            "Check the expected output and backup plan",
            "Prepare a concise closing summary",
            "Verify the room, device, and connection",
            "Keep supporting notes easy to find",
            "Leave time for questions",
            "Capture follow-up actions",
            "Confirm the next-step owner",
            "Review the final run once more",
        ][:count]
        return "\n".join(
            ["# Demo checklist", ""]
            + [f"{index}. {item}" for index, item in enumerate(checklist, 1)]
        ), "LOCAL"

    return (
        "NOT EXECUTED\n"
        "No available local execution tool can complete this deliverable. "
        "The request remains unmet; no successful result is claimed.",
        "LOCAL",
    )


def mark_execution_interrupted(mission, recovery_only=False):
    message = "Execution stream disconnected before the mission finished."
    for run in mission.get("tool_runs", []):
        if run.get("status") == "running":
            run.update(status="interrupted", finished_at=now(), error=message)
    mission["status"] = "interrupted"
    if recovery_only and mission.get("recovery"):
        mission["recovery"]["status"] = "interrupted"
    log(mission, "execution_interrupted", message, {"recovery": recovery_only})


# ============================================================
# VERIFICATION
# ============================================================

# Verifier name -> function(spec, task_evidence, latest_by_task, contract)
# returning (passed, reason). Unregistered verifiers fail closed.
VERIFIERS = verifiers.VERIFIERS


def verify_typed(contract, evidence):
    latest = {}
    for item in evidence:
        if isinstance(item, dict):
            latest[item.get("step")] = item

    requirement_results = []
    for spec in contract.get("requirement_specs", []):
        task_id = trip_tools.REQUIREMENT_TASK[spec["type"]]
        record = latest.get(task_id)
        verifier = VERIFIERS.get(spec["verifier"])
        if not record:
            passed = False
            reason = f"Task {task_id} produced no evidence."
        elif verifier is None:
            passed = False
            reason = f"Verifier {spec['verifier']} is not registered; the result cannot be confirmed."
        else:
            # The verifier inspects the real artifact; the tool's own status
            # is not consulted.
            try:
                passed, reason = verifier(spec, record, latest, contract)
            except Exception as exc:
                passed, reason = False, f"{spec['verifier']} could not complete ({type(exc).__name__}: {clip(exc, 200)})."
        requirement_results.append({
            "requirement": spec["description"],
            "requirement_id": spec["id"],
            "verifier": spec["verifier"],
            "evidence_id": (record or {}).get("id"),
            "status": "satisfied" if passed else "missing",
            "reason": reason,
            "affected_task": trip_tools.TASKS[task_id]["tool"],
        })

    missing = [item["requirement"] for item in requirement_results if item["status"] != "satisfied"]
    satisfied = [item["requirement"] for item in requirement_results if item["status"] == "satisfied"]
    return ({
        "passed": bool(requirement_results) and not missing,
        "score": len(satisfied) / len(requirement_results) if requirement_results else 0,
        "satisfied": satisfied,
        "missing": missing,
        "requirement_results": requirement_results,
        "warnings": [],
    }, "LOCAL")


def verify(
    goal,
    contract,
    output,
    evidence,
):
    if contract.get("requirement_specs"):
        return verify_typed(contract, evidence)

    requirement_results = []
    completed_tools = {
        item.get("tool")
        for item in evidence
        if isinstance(item, dict) and item.get("status") == "complete"
    }
    failed_tools = {
        item.get("tool")
        for item in evidence
        if isinstance(item, dict) and item.get("status") == "failed"
    }
    research_outputs = [
        item.get("output", "")
        for item in evidence
        if isinstance(item, dict) and item.get("tool") == "research"
    ]

    for requirement in contract.get("requirements", []):
        lowered = requirement.casefold()
        affected = "content"
        reason = "No supported local deliverable was produced for this requirement."
        satisfied = False

        if re.search(
            r"\b(research|latest|current|compare|technology|market|sources?|cite|news|price|pricing)\b",
            lowered,
        ):
            affected = "research"
            if "research" in completed_tools and not any(
                "RESEARCH BLOCKED" in text or "NOT VERIFIED" in text
                for text in research_outputs
            ) and any(re.search(r"https?://\S+", text) for text in research_outputs):
                satisfied = True
                reason = "Research evidence completed with at least one source URL."
            elif "research" in failed_tools:
                reason = "The research tool failed or returned no verifiable evidence."
            else:
                reason = "Research evidence with source URLs is missing."
        elif re.search(
            r"\b(workspace|repo|repository|project|code|files|app|website)\b",
            lowered,
        ) and re.search(
            r"\b(inspect|scan|review|analyze|audit|list|count|find)\b",
            lowered,
        ) and not re.search(
            r"\b(create|generate|produce|prepare|build|write|draft|summarize|roadmap)\b",
            lowered,
        ):
            affected = "workspace"
            satisfied = "workspace" in completed_tools
            reason = (
                "Workspace inspection completed."
                if satisfied
                else "Workspace inspection did not complete."
            )
        elif re.search(r"\b(checklist|to-do list|todo list)\b", lowered):
            affected = "content"
            item_count = len(re.findall(r"(?m)^\s*\d+[.)]\s+", output))
            count_match = re.search(
                r"\b(\d{1,2})\s*(?:-\s*)?(?:point|item|step)s?\b",
                lowered,
            )
            expected = min(10, max(1, int(count_match.group(1)))) if count_match else 3
            satisfied = (
                "content" in completed_tools
                and "# demo checklist" in output.casefold()
                and item_count >= expected
            )
            reason = (
                f"Checklist contains {item_count} numbered items; {expected} required."
                if not satisfied
                else f"Checklist contains the required {expected} numbered items."
            )
        elif "content" in completed_tools and not output.startswith("NOT EXECUTED"):
            satisfied = True
            reason = "A content deliverable was produced for this requirement."
        elif "content" in failed_tools:
            reason = "The content tool failed to produce the requested deliverable."

        requirement_results.append({
            "requirement": requirement,
            "status": "satisfied" if satisfied else "missing",
            "reason": reason,
            "affected_task": affected,
        })

    missing = [
        item["requirement"]
        for item in requirement_results
        if item["status"] != "satisfied"
    ]
    satisfied = [
        item["requirement"]
        for item in requirement_results
        if item["status"] == "satisfied"
    ]
    passed = bool(requirement_results) and not missing
    return ({
        "passed": passed,
        "score": len(satisfied) / len(requirement_results) if requirement_results else 0,
        "satisfied": satisfied,
        "missing": missing,
        "requirement_results": requirement_results,
        "warnings": [
            "Verification checks requirement-specific tool evidence and output criteria; factual claims are not independently validated."
        ],
    }, "LOCAL")


# ============================================================
# RECOVERY PLANNER
# ============================================================

def create_recovery_plan(
    mission,
):
    verification = (
        mission.get(
            "verification"
        )
        or {}
    )
    requirement_results = verification.get("requirement_results", [])
    missing = [item for item in requirement_results if item.get("status") != "satisfied"]
    steps = mission.get("steps", [])
    recoverable = {
        step.get("tool") for step in steps
        if step.get("tool") not in {"mission", "verification"}
    } | {"research", "workspace", "content"}
    affected = list(dict.fromkeys(
        item.get("affected_task", "content")
        for item in missing
        if item.get("affected_task") in recoverable
    ))
    if not affected:
        affected = ["content"]

    # A failed upstream task must be retried before its dependents can run.
    ids_by_tool = {step.get("tool"): step.get("id") for step in steps}
    steps_by_id = {step.get("id"): step for step in steps}
    latest = latest_evidence(mission)
    affected_ids = {ids_by_tool[tool] for tool in affected if tool in ids_by_tool}
    pending = list(affected_ids)
    while pending:
        for dependency in steps_by_id.get(pending.pop(), {}).get("depends_on", []):
            if dependency in affected_ids or dependency not in steps_by_id:
                continue
            if steps_by_id[dependency].get("tool") in {"mission", "verification"}:
                continue
            if (latest.get(dependency) or {}).get("status") != "complete":
                affected_ids.add(dependency)
                pending.append(dependency)

    # A repaired upstream task invalidates the outputs of its graph dependents.
    # Expand by dependency edges so research/workspace recovery also rebuilds
    # content that consumed those results, while leaving unrelated branches alone.
    changed = True
    while changed:
        changed = False
        for step in steps:
            if step.get("tool") == "verification" or step.get("id") in affected_ids:
                continue
            if any(dependency in affected_ids for dependency in step.get("depends_on", [])):
                affected_ids.add(step.get("id"))
                changed = True
    affected = list(dict.fromkeys(
        step.get("tool") for step in steps
        if step.get("id") in affected_ids and step.get("tool") in recoverable
    ))

    actions_by_tool = {
        "research": "Retry research and require source URLs before using its claims.",
        "workspace": "Repeat workspace inspection and record the resulting snapshot.",
        "content": "Rebuild the requested deliverable from verified mission evidence.",
    }
    plan = {
        "reason": "One or more mission requirements lack successful supporting evidence.",
        "missing_requirements": [item.get("requirement", "") for item in missing],
        "requirement_results": missing,
        "affected_tasks": affected,
        "recovery_actions": [
            actions_by_tool.get(tool, f"Re-run {TOOL_POLICY.get(tool, {}).get('name', tool)} and record fresh evidence.")
            for tool in affected
        ],
        "approval_required": True,
        "max_attempts": MAX_RECOVERY_ATTEMPTS,
        "provider": "LOCAL",
    }
    return plan


# ============================================================
# EXECUTION ENGINE
# ============================================================

async def execute_mission(
    mission,
    recovery_only=False,
    only_steps=None,
):
    # only_steps re-runs a chosen subset (stale tasks after a contract change)
    # without consuming a recovery attempt.
    trigger = "recovery" if recovery_only else "change" if only_steps is not None else "initial"
    llm_phase = "recovery" if recovery_only else "execution"

    if not recovery_only and mission.get("approval", {}).get("status") != "approved":
        raise HTTPException(status_code=403, detail="Mission execution requires explicit human approval.")

    mission[
        "status"
    ] = (
        "recovering"
        if recovery_only
        else "executing"
    )

    yield event(
        "mission",
        {
            "mission": mission
        },
    )

    evidence = [
        item.get("output", "")
        for item in mission.get("evidence", [])
        if recovery_only
        and item.get("status") == "complete"
        and item.get("tool") != "verification"
    ]

    if recovery_only or only_steps is not None:
        affected = set(
            (mission.get("recovery") or {})
            .get("plan", {})
            .get("affected_tasks", [])
        )
        steps = [
            step
            for step in mission[
                "steps"
            ]
            if (step["id"] in only_steps if only_steps is not None else step["tool"] in affected)
            and step["tool"] != "verification"
        ]
        verification_step = next(
            (step for step in mission["steps"] if step["tool"] == "verification"),
            {"id": "verify", "title": "Verify mission", "tool": "verification", "depends_on": []},
        )
        steps.append(verification_step)
        mission["verification"] = None

    else:
        steps = mission[
            "steps"
        ]

    for step in steps:

        route = route_tool(step, mission)
        route_record = {
            **route,
            "status": "running",
            "started_at": now(),
            "finished_at": None,
            "output": None,
            "error": None,
            "recovery": recovery_only,
        }
        mission.setdefault("tool_runs", []).append(route_record)
        log(mission, "tool_routed", f"{step['title']} routed to {route['tool']}.", {**route, "task_id": step["id"], "recovery": recovery_only})

        latest_by_step = {}
        for item in mission.get("evidence", []):
            latest_by_step[item.get("step")] = item.get("status")
        completed = {key for key, value in latest_by_step.items() if value == "complete"}
        stale = {key for key, value in latest_by_step.items() if value == "stale"}
        unmet_dependencies = [dep for dep in step.get("depends_on", []) if dep not in completed or dep in stale]

        if unmet_dependencies and step["tool"] != "verification":
            reason = f"Dependency tasks are not complete: {', '.join(unmet_dependencies)}."
            route_record.update(status="blocked", finished_at=now(), error=reason)
            mission["evidence"].append({"id": f"ev{len(mission['evidence']) + 1}", "step": step["id"], "tool": step["tool"], "provider": "LOCAL", "status": "failed", "recovery": recovery_only, "trigger": trigger, "output": reason, "inputs": route["inputs"], "permissions": route["permissions"], "risk": route["risk"], "started_at": route_record["started_at"], "finished_at": route_record["finished_at"]})
            log(mission, "task_blocked", step["title"], {"tool": step["tool"], "unmet_dependencies": unmet_dependencies, "recovery": recovery_only})
            yield event("task_failed", {"task": step, "provider": "LOCAL", "output": reason, "recovery": recovery_only, "reason": reason})
            continue

        log(
            mission,
            "task_start",
            step["title"],
            {
                "tool": step["tool"],
                "recovery": recovery_only,
            },
        )

        yield event(
            "task_start",
            {
                "task": step,
                "recovery": recovery_only,
            },
        )

        await asyncio.sleep(
            0.25
        )

        tool = step["tool"]

        task_status = "complete"
        tool_data = None
        upstream_ids = {}
        try:
            if tool in trip_tools.TOOLS:

                latest = latest_evidence(mission)
                upstream = {}
                for dep in step.get("depends_on", []):
                    record = latest.get(dep)
                    if record and record.get("data") is not None:
                        upstream[dep] = record["data"]
                        upstream_ids[dep] = record.get("id")

                output, tool_data = await asyncio.to_thread(
                    trip_tools.run_tool,
                    tool,
                    {
                        "mission_id": mission["id"],
                        "params": route["inputs"].get("parameters", {}),
                        "upstream": upstream,
                    },
                )
                provider = "LOCAL"

            elif tool == "mission":

                output = json.dumps(
                    mission["contract"],
                    indent=2,
                    ensure_ascii=False,
                )

                provider = mission["provider"]

            elif tool == "workspace":

                current = await asyncio.to_thread(scan_workspace)

                changes = workspace_delta(mission["workspace"], current)

                mission["workspace"] = current

                output = (
                    f"Workspace: {current['root']}\n"
                    f"Files: {len(current['files'])}\n"
                    f"Changes: {json.dumps(changes)}"
                )

                provider = "LOCAL"

            elif tool == "research":

                output, provider = await asyncio.to_thread(
                    research,
                    mission["goal"],
                    llm_phase,
                    mission.setdefault("llm_calls", new_llm_counter()),
                )

            elif tool == "content":
                if mission.get("demo_mode") and not recovery_only and not mission.get("demo_failure_injected"):
                    output = "DEMO FAILURE (INTENTIONAL): The local draft tool was configured to fail once so the recovery path can be demonstrated. No deliverable was produced on this attempt."
                    provider = "LOCAL DEMO FIXTURE"
                    task_status = "failed"
                    mission["demo_failure_injected"] = True
                else:
                    output, provider = await asyncio.to_thread(
                        synthesize,
                        mission["goal"],
                        mission["contract"],
                        evidence,
                        not mission.get("demo_mode"),
                        llm_phase,
                        mission.setdefault("llm_calls", new_llm_counter()),
                    )

                    if not output.startswith("NOT EXECUTED"):
                        mission["artifacts"].append(output)

            elif tool == "verification":

                if mission["contract"].get("requirement_specs"):
                    mission["artifacts"].append(trip_tools.mission_summary(
                        mission["contract"],
                        {
                            task_id: record["data"]
                            for task_id, record in latest_evidence(mission).items()
                            if record.get("status") == "complete" and record.get("data") is not None
                        },
                    ))

                final_output = mission["artifacts"][-1] if mission["artifacts"] else ""

                verification, provider = await asyncio.to_thread(
                    verify,
                    mission["goal"],
                    mission["contract"],
                    final_output,
                    mission["evidence"],
                )

                mission["verification"] = verification

                output = json.dumps(verification, indent=2, ensure_ascii=False)

            else:

                output = "Unknown HADES tool."
                provider = "LOCAL"
                task_status = "failed"

            if tool == "research" and (
                "RESEARCH BLOCKED" in output
                or not re.search(r"https?://\S+", output)
            ):
                task_status = "failed"
            if tool == "content" and output.startswith("NOT EXECUTED"):
                task_status = "failed"

        except trip_tools.ToolError as exc:
            output = f"{tool} tool failed: {exc}"
            provider = "LOCAL"
            task_status = "failed"
        except Exception as exc:
            output = f"{tool} tool failed ({type(exc).__name__})."
            provider = "LOCAL"
            task_status = "failed"

        mission[
            "evidence"
        ].append(
            {
                "id": f"ev{len(mission['evidence']) + 1}",
                "step": step["id"],
                "data": tool_data,
                "upstream_evidence": upstream_ids,
                "trigger": trigger,
                "tool": tool,
                "provider": provider,
                "status": task_status,
                "recovery": recovery_only,
                "inputs": route["inputs"],
                "permissions": route["permissions"],
                "risk": route["risk"],
                "started_at": route_record["started_at"],
                "finished_at": now(),
                "output": clip(
                    output,
                    14000,
                ),
            }
        )

        route_record.update(
            status=task_status,
            finished_at=now(),
            output=clip(output, 14000) if task_status == "complete" else None,
            error=clip(output, 4000) if task_status == "failed" else None,
            provider=provider,
        )

        evidence.append(
            output
        )

        result_event = "task_complete" if task_status == "complete" else "task_failed"
        log(
            mission,
            result_event,
            step["title"],
            {
                "tool": tool,
                "provider": provider,
                "recovery": recovery_only,
            },
        )

        yield event(
            result_event,
            {
                "task": step,
                "provider": provider,
                "output": clip(output, 5000),
                "recovery": recovery_only,
                "reason": output if task_status == "failed" else None,
            },
        )

        await asyncio.sleep(
            0.2
        )

    verification = mission.get(
        "verification"
    )

    if verification is None:
        verification = {
            "passed": False,
            "score": 0,
            "satisfied": [],
            "missing": ["Verification tool failed to produce a result."],
            "requirement_results": [{
                "requirement": "Verification result",
                "status": "missing",
                "reason": "The verification task failed.",
                "affected_task": "verification",
            }],
            "warnings": ["Mission cannot complete without a verification result."],
        }
        mission["verification"] = verification

    auto_retry = False
    typed = bool(mission["contract"].get("requirement_specs"))
    options = (
        amendments.propose(mission["contract"], verification)
        if typed and verification and not verification.get("passed")
        else []
    )

    if options:
        # A constraint cannot be met inside the current contract. Retrying is
        # pointless; offer amendments, which always need human approval.
        if len(mission["contract"].get("amendments", [])) >= MAX_AMENDMENTS:
            mission["status"] = "blocked"
            mission["recovery"] = {
                "status": "blocked",
                "kind": "amendment",
                "reason": f"The contract was already amended {MAX_AMENDMENTS} times and a constraint still fails.",
                "verification": verification,
                "attempts": mission.get("recovery_attempts", 0),
            }
            log(mission, "blocked", mission["recovery"]["reason"], mission["recovery"])
            yield event("blocked", {"recovery": mission["recovery"]})
        else:
            recovery_plan = create_recovery_plan(mission)
            steps = mission.get("steps", [])
            for option in options:
                option["rerun_preview"] = stale_closure(steps, option["diff"])
            failed = [item for item in verification.get("requirement_results", []) if item.get("status") != "satisfied"]
            mission["recovery"] = {
                "status": "approval_required",
                "kind": "amendment",
                "trigger": "constraint_failed",
                "reason": "A contract constraint cannot be met as written. Choose an amendment or reject all options.",
                "missing_requirements": [item["requirement"] for item in failed],
                "requirement_results": failed,
                "verification": verification,
                "options": options,
                "affected_tasks": recovery_plan["affected_tasks"],
                "actions": [option["label"] for option in options],
                "attempts": mission.get("recovery_attempts", 0),
                "plan": {**recovery_plan, "approval_required": True},
            }
            mission["status"] = "recovery_required"
            log(mission, "amendment_required", "Constraint failure. Contract amendment options await approval.", {
                "options": [{"id": option["id"], "diff": option["diff"]} for option in options],
            })
            yield event("recovery_required", {"recovery": mission["recovery"]})

    elif (
        verification
        and not verification.get(
            "passed"
        )
    ):
        if mission.get("recovery_attempts", 0) >= MAX_RECOVERY_ATTEMPTS:
            mission["status"] = "blocked"
            mission["recovery"] = {
                **(mission.get("recovery") or {}),
                "status": "blocked",
                "reason": "The approved recovery attempt did not satisfy every requirement.",
                "verification": verification,
                "attempts": mission.get("recovery_attempts", 0),
            }
            log(mission, "blocked", mission["recovery"]["reason"], mission["recovery"])
            yield event("blocked", {"recovery": mission["recovery"]})
        elif typed:
            # A retry inside the contract changes nothing the human agreed
            # to, so it runs without approval but still counts as an attempt.
            recovery_plan = create_recovery_plan(mission)
            mission["recovery_attempts"] = mission.get("recovery_attempts", 0) + 1
            mission["recovery"] = {
                "status": "executing",
                "kind": "retry",
                "trigger": "verification_failed",
                "approval_required": False,
                "missing_requirements": verification.get("missing", []),
                "requirement_results": verification.get("requirement_results", []),
                "verification": verification,
                "affected_tasks": recovery_plan["affected_tasks"],
                "actions": recovery_plan["recovery_actions"],
                "attempts": mission["recovery_attempts"],
                "reason": "Retrying failed tasks inside the contract; no approval needed.",
                "plan": {**recovery_plan, "approval_required": False},
            }
            mission["status"] = "recovering"
            log(mission, "recovery_auto_started", mission["recovery"]["reason"], recovery_plan)
            auto_retry = True
        else:
            recovery_plan = create_recovery_plan(mission)
            mission["recovery"] = {
                "status": "approval_required",
                "trigger": "verification_failed",
                "verification_score": verification.get("score", 0),
                "missing_requirements": verification.get("missing", []),
                "requirement_results": verification.get("requirement_results", []),
                "warnings": verification.get("warnings", []),
                "verification": verification,
                "affected_tasks": recovery_plan["affected_tasks"],
                "actions": recovery_plan["recovery_actions"],
                "attempts": mission.get("recovery_attempts", 0),
                "reason": recovery_plan["reason"],
                "plan": recovery_plan,
            }
            mission["status"] = "recovery_required"
            log(mission, "recovery_required", "Verification failed. Targeted recovery is awaiting approval.", mission["recovery"])
            yield event("recovery_required", {"recovery": mission["recovery"]})

    elif verification:

        mission[
            "status"
        ] = "complete"
        log(mission, "mission_complete", "All mission requirements passed verification.", {"verification_score": verification.get("score")})

        if mission.get(
            "recovery"
        ):
            mission[
                "recovery"
            ][
                "status"
            ] = "resolved"

    yield event(
        "verification",
        {
            "verification": mission.get(
                "verification"
            )
        },
    )
    log(mission, "verification_passed" if verification.get("passed") else "verification_failed", "Requirement verification completed.", verification)

    if auto_retry:
        yield event("recovery", {"message": mission["recovery"]["reason"], "plan": mission["recovery"]["plan"], "approval_required": False})
        async for item in execute_mission(mission, recovery_only=True):
            yield item
        log(mission, "recovery_finished", "Automatic retry finished.", {"status": mission.get("status"), "attempts": mission.get("recovery_attempts")})
        return

    final_solution = (
        mission[
            "artifacts"
        ][-1]
        if mission[
            "artifacts"
        ]
        else "No deliverable produced."
    )

    yield event(
        "solution",
        {
            "solution": final_solution,
            "mode": mission.get(
                "provider",
                "LOCAL",
            ),
        },
    )

    yield event(
        "complete",
        {
            "status": mission[
                "status"
            ],
            "mission_id": mission[
                "id"
            ],
            "verification": mission.get(
                "verification"
            ),
            "recovery": mission.get(
                "recovery"
            ),
            "evidence_count": len(
                mission[
                    "evidence"
                ]
            ),
            "llm_calls": llm_summary(mission.get("llm_calls")),
        },
    )


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
def root():

    return {
        "status": "online",
        "agent": "HADES CORE",
        "version": APP_VERSION,
        "gemini": bool(
            os.getenv(
                "GEMINI_API_KEY"
            )
        ),
        "groq": bool(
            os.getenv(
                "GROQ_API_KEY"
            )
        ),
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "version": APP_VERSION,
        "gemini": bool(
            os.getenv(
                "GEMINI_API_KEY"
            )
        ),
        "groq": bool(
            os.getenv(
                "GROQ_API_KEY"
            )
        ),
    }


@app.get("/tools")
def tools():

    return {
        "tools": [
            *(
                {
                    "id": tool_id,
                    "name": policy["name"],
                    "risk": policy["risk"],
                    "permissions": policy["permissions"],
                }
                for tool_id, policy in TOOL_POLICY.items()
            ),
            {
                "id": "recovery",
                "name": "Recovery Engine",
                "risk": "MEDIUM",
                "permissions": ["execute:approved-recovery", "human:approval"],
            },
        ]
    }


@app.get("/mission/state-from-workspace")
def state():

    return {
        "workspace": scan_workspace(),
        "missions": [
            {
                "id": mission["id"],
                "goal": mission["goal"],
                "status": mission["status"],
                "requirements": len(
                    mission["contract"].get("requirements", [])
                ),
                "evidence": len(mission["evidence"]),
                "verification_passed": (
                    mission.get("verification") or {}
                ).get("passed"),
                "recovery_status": (
                    mission.get("recovery") or {}
                ).get("status"),
                "recovery_attempts": mission.get("recovery_attempts", 0),
                "events": mission.get("events", []),
                "tool_runs": mission.get("tool_runs", []),
            }
            for mission in MISSIONS.values()
        ],
    }


@app.get("/mission/{mission_id}")
def get_mission(
    mission_id: str
):

    return MISSIONS.get(
        mission_id,
        {
            "status": "error",
            "message": "Mission not found.",
        },
    )


@app.post("/workspace/scan")
def workspace_scan():

    return {
        "status": "success",
        "snapshot": scan_workspace(),
    }


NOT_A_GOAL_MESSAGES = {
    "QUESTION": "That's a question, not a goal. HADES executes goals.",
    "CHAT": "That's a chat message, not a goal. HADES executes goals.",
}


def classify_input(text):
    """GOAL / QUESTION / CHAT. Rules always run; an enabled LLM may refine
    the kind and supply a one-line quick answer, but it can never turn a
    supported goal into a non-goal. Those calls count as "conversation"."""
    kind, reason = goal_compiler.classify_input(text)
    classifier = "rules"
    quick_answer = None
    supported_goal = goal_compiler.decompose_goal(text) is not None

    if ai_enhancements_enabled() and not supported_goal:
        reply, _ = llm_call(goal_compiler.classify_prompt(text), "conversation", purpose="general", json_mode=True)
        if reply:
            try:
                llm_kind, answer = goal_compiler.validate_classification(parse_json(reply))
                kind, classifier = llm_kind, "llm"
                reason = "Classified by the optional LLM."
                quick_answer = answer or None
            except ValueError as exc:
                print("[Classifier] LLM output rejected:", exc)

    result = {"kind": kind, "reason": reason, "classifier": classifier}
    if kind != "GOAL":
        result.update(
            message=NOT_A_GOAL_MESSAGES[kind],
            examples=list(goal_compiler.EXAMPLE_GOALS),
            quick_answer=quick_answer,
            quick_answer_label="Quick answer (not a mission)" if quick_answer else None,
            llm_conversation_calls=LLM_CALLS["conversation"],
        )
    return result


@app.post("/classify")
def classify(req: Goal):

    return classify_input(req.goal.strip())


@app.post("/plan")
def plan(req: Goal):

    goal = req.goal.strip()

    if not goal:
        return {
            "status": "error",
            "message": "Goal cannot be empty.",
        }

    if len(goal) > 4000:
        return {
            "status": "error",
            "message": "Goal is too long. Keep it under 4,000 characters.",
        }

    # Only goals become missions; questions and chat get a friendly reply.
    classification = classify_input(goal)
    if classification["kind"] != "GOAL":
        return {"status": "not_a_goal", **classification}

    mission = create_mission(
        goal
    )

    return {
        "status": "success",
        "mission_id": mission[
            "id"
        ],
        "plan": mission,
    }


@app.post("/demo/plan")
def demo_plan():
    """Create a repeatable local mission with one visibly simulated failure."""
    goal = "Create a 3 item checklist for a reliable HADES hackathon demo"
    mission = create_mission(goal)
    mission["demo_mode"] = True
    mission["demo_failure_injected"] = False
    mission["approval"]["reason"] = "Local demo mode. The first draft attempt intentionally fails once to demonstrate evidence-driven recovery."
    log(mission, "demo_fixture_enabled", "Provider-free demo fixture enabled; one initial content failure is deliberately simulated.", {"failure_count": 1, "ai_calls": False})
    return {"status": "success", "mission_id": mission["id"], "plan": mission}


@app.post(
    "/execute-approved-stream"
)
async def execute_approved(
    req: Approved
):

    mission = MISSIONS.get(
        req.plan.get("id")
    )

    if not mission or mission["goal"] != req.goal:
        raise HTTPException(status_code=404, detail="Plan not found or no longer matches the goal. Generate a fresh plan.")
    if not req.approved:
        mission["approval"]["status"] = "rejected"
        mission["status"] = "blocked"
        log(mission, "approval_rejected", "Human declined mission execution.", mission["approval"])
        raise HTTPException(status_code=403, detail="Mission execution was not approved.")
    if mission.get("approval", {}).get("status") == "approved" or mission.get("status") not in {"awaiting_approval", "planned"}:
        raise HTTPException(status_code=409, detail="Mission is not awaiting execution approval.")
    mission["approval"]["status"] = "approved"
    mission["approval"]["approved_at"] = now()
    log(mission, "approval_granted", "Human approved mission execution.", mission["approval"])

    async def stream():

        yield event(
            "goal",
            {
                "goal": req.goal
            },
        )

        yield event(
            "planning",
            {
                "message": (
                    "Human approval received. "
                    "Starting mission graph."
                )
            },
        )

        yield event(
            "plan",
            {
                "plan": mission
            },
        )

        try:
            async for item in execute_mission(mission):
                yield item
        except asyncio.CancelledError:
            mark_execution_interrupted(mission)
            raise
        except Exception as exc:
            mission["status"] = "blocked"
            log(mission, "execution_error", "Mission execution stopped after an internal error.", {"error": f"{type(exc).__name__}: {clip(exc, 500)}"})
            yield event("error", {"message": "Mission execution stopped safely. Inspect the mission audit timeline for details."})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# CHANGE DETECTION
# ============================================================

@app.post(
    "/mission/invalidate"
)
def invalidate(
    req: Change
):

    mission = MISSIONS.get(
        req.mission_id
    )

    if not mission:
        return {
            "status": "error",
            "message": "Mission not found.",
        }

    tracked_workspace_inputs = mission.get("contract", {}).get("needs_workspace") or any(
        item.get("inputs", {}).get("workspace_paths")
        for item in mission.get("evidence", [])
        if isinstance(item, dict)
    )
    if not tracked_workspace_inputs:
        return {"status": "success", "mission": mission, "message": "This mission has no tracked workspace inputs."}

    current = scan_workspace()

    changes = workspace_delta(
        mission[
            "workspace"
        ],
        current,
    )

    if not any(changes.get(kind) for kind in ("added", "removed", "changed")):
        return {"status": "success", "mission": mission, "message": "No workspace changes detected."}

    changed_paths = set(changes.get("changed", [])) | set(changes.get("added", [])) | set(changes.get("removed", []))
    impacted = []
    for result in (mission.get("verification") or {}).get("requirement_results", []):
        task = result.get("affected_task")
        requirement = result.get("requirement", "")
        # Workspace changes affect workspace inspection and deliverables that depend on that inspected context.
        if task in {"workspace", "content"} and (task == "workspace" or re.search(r"workspace|repo|repository|project|code|files|app|website", requirement, re.I)):
            impacted.append(result)
    affected_tasks = list(dict.fromkeys(item.get("affected_task") for item in impacted if item.get("affected_task") in {"workspace", "research", "content"}))
    if not affected_tasks:
        affected_tasks = ["workspace"] if any(step.get("tool") == "workspace" for step in mission.get("steps", [])) else ["content"]
    stale_evidence = []
    for item in mission.get("evidence", []):
        if item.get("status") != "complete":
            continue
        task = item.get("tool")
        associated = task in affected_tasks
        observed = set(item.get("inputs", {}).get("workspace_paths", []))
        if observed and observed.intersection(changed_paths):
            associated = True
        if associated:
            item["status"] = "stale"
            item["stale_at"] = now()
            item["stale_reason"] = req.reason
            stale_evidence.append(item.get("step"))
            if task in {"workspace", "research", "content"} and task not in affected_tasks:
                affected_tasks.append(task)
    mission["workspace"] = current
    affected_requirement_names = {item.get("requirement") for item in impacted}
    verification = mission.get("verification") or {}
    for result in verification.get("requirement_results", []):
        if result.get("requirement") in affected_requirement_names:
            result["status"] = "stale"
            result["reason"] = "Supporting evidence became stale after workspace changes."
    if affected_requirement_names:
        verification["passed"] = False
        verification["score"] = sum(1 for item in verification.get("requirement_results", []) if item.get("status") == "satisfied") / max(1, len(verification.get("requirement_results", [])))
    mission["verification"] = verification or None
    mission["change"] = {
        "reason": req.reason,
        "delta": changes,
        "changed_paths": sorted(changed_paths),
        "affected_requirements": sorted(affected_requirement_names),
        "affected_tasks": affected_tasks,
        "stale_evidence": stale_evidence,
    }

    mission[
        "recovery"
    ] = {
        "status": "approval_required",
        "trigger": "mission_changed",
        "reason": "Workspace inputs changed; linked requirement evidence is stale.",
        "missing_requirements": sorted(affected_requirement_names),
        "affected_tasks": affected_tasks,
        "actions": [
            "Revalidate changed evidence",
            "Re-execute affected work",
            "Rebuild affected deliverable",
            "Run verification again",
        ],
        "plan": {
            "reason": (
                "Mission input changed "
                "after execution."
            ),
            "affected_tasks": affected_tasks,
            "missing_requirements": sorted(affected_requirement_names),
            "approval_required": True,
        },
    }

    mission[
        "status"
    ] = "change_detected"

    log(
        mission,
        "change_detected",
        (
            "Mission input changed. "
            "Impact analysis completed."
        ),
        mission[
            "change"
        ],
    )
    log(mission, "stale_evidence", "Evidence tied to changed workspace inputs was marked stale.", mission["change"])
    log(mission, "recovery_required", "Targeted re-execution and re-verification require human approval.", mission["recovery"])

    return {
        "status": "success",
        "mission": mission,
    }


# ============================================================
# CONTRACT PARAMETER CHANGES
# ============================================================

def stale_closure(steps, changed_keys):
    """Tasks that read a changed parameter, plus everything downstream of
    them in the dependency graph, in execution order."""
    affected = {
        step["id"] for step in steps
        if step.get("tool") != "verification" and set(step.get("reads", [])) & set(changed_keys)
    }
    changed = True
    while changed:
        changed = False
        for step in steps:
            if step.get("tool") == "verification" or step["id"] in affected:
                continue
            if any(dependency in affected for dependency in step.get("depends_on", [])):
                affected.add(step["id"])
                changed = True
    return [step["id"] for step in steps if step["id"] in affected]


def apply_contract_change(mission, changes, source, extra_steps=()):
    """Update contract parameters, mark dependent evidence stale and plan the
    targeted re-run. extra_steps adds tasks that must re-run for another
    reason (for example, they failed). Returns the change record, or None if
    nothing changed."""
    contract = mission["contract"]
    parameters = contract.setdefault("parameters", {})
    diff = {
        key: {"before": parameters.get(key), "after": value}
        for key, value in changes.items()
        if parameters.get(key) != value
    }
    if not diff:
        return None

    reason = "; ".join(f"{key} changed: {item['before']} → {item['after']}" for key, item in diff.items())
    for key in diff:
        parameters[key] = changes[key]
    specs = contract.get("requirement_specs", [])
    for spec in specs:
        goal_compiler.refresh_requirement(spec, parameters)
    contract["requirements"] = [spec["description"] for spec in specs]
    contract["deliverables"] = [spec["description"] for spec in specs]
    contract["constraints"] = [
        item for item in contract.get("constraints", [])
        if not item.startswith("Total trip cost must not exceed")
    ] + (
        [f"Total trip cost must not exceed ₹{parameters['max_budget']:,}"]
        if parameters.get("max_budget") is not None and any(spec["type"] == "budget" for spec in specs)
        else []
    )

    steps = mission.get("steps", [])
    rerun_ids = set(stale_closure(steps, diff)) | set(extra_steps)
    rerun = [step["id"] for step in steps if step["id"] in rerun_ids and step.get("tool") != "verification"]
    latest = latest_evidence(mission)
    stale_evidence = []
    for step_id in rerun:
        record = latest.get(step_id)
        if record and record.get("status") == "complete":
            record.update(status="stale", stale_at=now(), stale_reason=reason)
            stale_evidence.append({"id": record.get("id"), "step": step_id})

    stale_requirements = sorted({
        requirement_id
        for step in steps if step["id"] in rerun
        for requirement_id in step.get("requirements", [])
    })
    descriptions = {spec["id"]: spec["description"] for spec in specs}
    verification = mission.get("verification")
    if verification:
        stale_ids = {item["id"]: item["step"] for item in stale_evidence}
        for result in verification.get("requirement_results", []):
            requirement_id = result.get("requirement_id")
            result["requirement"] = descriptions.get(requirement_id, result.get("requirement"))
            if requirement_id in stale_requirements:
                result["status"] = "stale"
                result["reason"] = (
                    f"Evidence {result.get('evidence_id')} is stale ({reason})."
                    if result.get("evidence_id") in stale_ids
                    else f"Must be re-checked ({reason})."
                )
        results = verification.get("requirement_results", [])
        verification["passed"] = False
        verification["satisfied"] = [item["requirement"] for item in results if item["status"] == "satisfied"]
        verification["missing"] = [item["requirement"] for item in results if item["status"] != "satisfied"]
        verification["score"] = len(verification["satisfied"]) / max(1, len(results))

    total = sum(1 for step in steps if step.get("tool") != "verification")
    record = {
        "trigger": "parameter_change",
        "source": source,
        "at": now(),
        "reason": reason,
        "diff": diff,
        "rerun_steps": rerun,
        "unaffected_steps": [step["id"] for step in steps if step.get("tool") != "verification" and step["id"] not in rerun],
        "rerun_count": len(rerun),
        "total_tasks": total,
        "stale_evidence": stale_evidence,
        "stale_requirements": stale_requirements,
        "message": f"Re-executing {len(rerun)} of {total} tasks",
    }
    mission["change"] = record
    mission.setdefault("changes", []).append(record)
    mission["reexecution"] = {"rerun": len(rerun), "total": total, "steps": rerun, "trigger": "parameter_change"}
    if mission.get("recovery") and mission["recovery"].get("status") == "approval_required":
        mission["recovery"]["status"] = "superseded"
        log(mission, "recovery_superseded", "A contract change replaced the pending recovery.", {"change": diff})

    log(mission, "contract_changed", reason, {"diff": diff, "source": source})
    log(mission, "evidence_stale", f"{len(stale_evidence)} evidence record(s) marked stale.", {
        "stale_evidence": stale_evidence,
        "stale_requirements": stale_requirements,
        "unaffected_steps": record["unaffected_steps"],
    })
    log(mission, "reexecution_planned", record["message"], {"rerun_steps": rerun})
    return record


class ParameterChange(BaseModel):
    changes: Optional[dict] = None
    text: Optional[str] = None


@app.post("/mission/{mission_id}/change")
async def change_mission(mission_id: str, req: ParameterChange):

    mission = MISSIONS.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")
    if not mission.get("contract", {}).get("requirement_specs"):
        raise HTTPException(status_code=400, detail="This mission has no typed parameters to change.")
    if mission.get("status") not in {"complete", "recovery_required", "blocked"}:
        raise HTTPException(status_code=409, detail=f"Mission is {mission.get('status')}; changes apply after execution finishes.")

    parameters = mission["contract"].get("parameters", {})
    date_key = "exam_date" if "exam_date" in parameters else "trip_date"
    raw = {}
    if req.text:
        # Chat text is parsed loosely; keep only parameters this contract has.
        parsed = goal_compiler.parse_change_text(clip(req.text, 500), date_key=date_key)
        raw.update({key: value for key, value in parsed.items() if key in parameters})
    explicit = req.changes or {}
    foreign = sorted(set(explicit) - set(parameters))
    if foreign:
        raise HTTPException(status_code=400, detail=f"This mission has no {', '.join(foreign)} to change.")
    raw.update(explicit)
    if not raw:
        example = "\"exam moved to Wednesday\"" if date_key == "exam_date" else "\"trip moved to Sunday\" or \"budget ₹4,600\""
        raise HTTPException(status_code=400, detail=f"No supported change found. Try {example}.")
    try:
        changes = goal_compiler.normalize_changes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    record = apply_contract_change(mission, changes, source="chat" if req.text else "api")
    if record is None:
        raise HTTPException(status_code=400, detail="Those values already match the mission contract.")

    async def stream():

        yield event("change", {"change": record, "mission": mission})

        try:
            async for item in execute_mission(mission, only_steps=record["rerun_steps"]):
                yield item
        except asyncio.CancelledError:
            mark_execution_interrupted(mission)
            raise
        except Exception as exc:
            mission["status"] = "blocked"
            log(mission, "execution_error", "Re-execution stopped after an internal error.", {"error": f"{type(exc).__name__}: {clip(exc, 500)}"})
            yield event("error", {"message": "Re-execution stopped safely. Inspect the mission audit timeline for details."})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# CONTRACT AMENDMENTS
# ============================================================

class AmendmentDecision(BaseModel):
    option_id: Optional[str] = None
    reject: bool = False


@app.post("/mission/{mission_id}/amend")
async def amend_mission(mission_id: str, req: AmendmentDecision):

    mission = MISSIONS.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")
    recovery = mission.get("recovery") or {}
    if recovery.get("kind") != "amendment" or recovery.get("status") != "approval_required":
        raise HTTPException(status_code=409, detail="No contract amendment is awaiting a decision.")

    if req.reject:
        recovery["status"] = "rejected"
        recovery["reason"] = "Every amendment option was rejected; the contract cannot be met as written."
        mission["status"] = "blocked"
        log(mission, "amendment_rejected", recovery["reason"], {"options": [option["id"] for option in recovery.get("options", [])]})
        return {"status": "success", "mission": mission}

    option = next((item for item in recovery.get("options", []) if item["id"] == req.option_id), None)
    if not option:
        raise HTTPException(status_code=400, detail=f"Unknown amendment option {req.option_id!r}.")
    try:
        changes = goal_compiler.normalize_changes({key: item["after"] for key, item in option["diff"].items()})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Tasks that failed for other reasons re-run alongside the amendment.
    ids_by_tool = {step.get("tool"): step["id"] for step in mission.get("steps", [])}
    retry_steps = [ids_by_tool[tool] for tool in recovery.get("affected_tasks", []) if tool in ids_by_tool]

    recovery["status"] = "approved"
    record = apply_contract_change(mission, changes, source=f"amendment:{option['id']}", extra_steps=retry_steps)
    if record is None:
        recovery["status"] = "approval_required"
        raise HTTPException(status_code=400, detail="That amendment matches the current contract.")
    recovery["status"] = "amended"
    recovery["chosen"] = option
    amendment = {
        "option_id": option["id"],
        "label": option["label"],
        "diff": option["diff"],
        "requirement_id": option.get("requirement_id"),
        "approved_at": now(),
    }
    mission["contract"].setdefault("amendments", []).append(amendment)
    log(mission, "amendment_approved", f"Human approved amendment: {option['label']}.", amendment)

    async def stream():

        yield event("amendment", {"amendment": amendment, "change": record, "mission": mission})

        try:
            async for item in execute_mission(mission, only_steps=record["rerun_steps"]):
                yield item
        except asyncio.CancelledError:
            mark_execution_interrupted(mission)
            raise
        except Exception as exc:
            mission["status"] = "blocked"
            log(mission, "execution_error", "Amended re-execution stopped after an internal error.", {"error": f"{type(exc).__name__}: {clip(exc, 500)}"})
            yield event("error", {"message": "Re-execution stopped safely. Inspect the mission audit timeline for details."})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# APPROVE RECOVERY
# ============================================================

@app.post(
    "/workspace/approve-recovery"
)
def approve_recovery(
    req: Recovery
):

    mission = MISSIONS.get(
        req.mission_id
    )

    if not mission:
        return {
            "status": "error",
            "message": "Mission not found.",
        }

    recovery = mission.get("recovery")
    if not recovery or recovery.get("status") != "approval_required":
        return {
            "status": "error",
            "message": (
                "No pending recovery approval exists."
            ),
        }

    if mission.get("recovery_attempts", 0) >= MAX_RECOVERY_ATTEMPTS:
        return {
            "status": "error",
            "message": "The recovery attempt limit has been reached.",
        }

    if not req.approved:

        recovery["status"] = "rejected"
        mission["status"] = "blocked"
        recovery["reason"] = "Human approval was declined."
        log(mission, "recovery_rejected", recovery["reason"], recovery)

        return {
            "status": "success",
            "mission": mission,
        }

    if recovery.get("kind") == "amendment":
        return {
            "status": "error",
            "message": "This recovery changes the contract. Choose an amendment option via /mission/{id}/amend.",
        }

    recovery["status"] = "approved"
    mission["status"] = "recovering"

    log(
        mission,
        "recovery_approved",
        (
            "Human approved the "
            "targeted recovery plan."
        ),
    )

    return {
        "status": "success",
        "mission": mission,
    }


# ============================================================
# REEXECUTE RECOVERY
# ============================================================

@app.post(
    "/mission/reexecute/{mission_id}"
)
async def reexecute(
    mission_id: str
):

    mission = MISSIONS.get(
        mission_id
    )

    if not mission:
        return {
            "status": "error",
            "message": "Mission not found.",
        }

    recovery = mission.get(
        "recovery"
    )

    if (
        not recovery
        or recovery.get(
            "status"
        )
        != "approved"
    ):
        return {
            "status": "error",
            "message": (
                "Recovery approval required."
            ),
        }

    # Claim the single recovery slot before starting the stream so duplicate
    # requests cannot run the same recovery twice.
    mission["recovery_attempts"] = mission.get("recovery_attempts", 0) + 1
    recovery["attempts"] = mission["recovery_attempts"]
    recovery["status"] = "executing"
    mission["status"] = "recovering"
    log(mission, "recovery_started", "Approved targeted recovery execution started.", recovery.get("plan", {}))

    async def stream():

        yield event(
            "recovery",
            {
                "message": (
                    "HADES is executing "
                    "only affected work."
                ),
                "plan": recovery.get(
                    "plan",
                    {},
                ),
            },
        )

        try:
            async for item in execute_mission(mission, recovery_only=True):
                yield item
        except asyncio.CancelledError:
            mark_execution_interrupted(mission, recovery_only=True)
            raise
        except Exception as exc:
            mission["status"] = "blocked"
            recovery["status"] = "blocked"
            recovery["reason"] = "Recovery execution stopped after an internal error."
            log(mission, "recovery_error", recovery["reason"], {"error": f"{type(exc).__name__}: {clip(exc, 500)}"})
            yield event("error", {"message": "Recovery execution stopped safely. Inspect the mission audit timeline for details."})

        log(mission, "recovery_finished", "Targeted recovery execution finished.", {"status": mission.get("status"), "attempts": mission.get("recovery_attempts")})

        if mission.get(
            "change"
        ):
            mission[
                "change"
            ] = None

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# RECEIPT
# ============================================================

def llm_summary(counter):
    counts = {phase: (counter or {}).get(phase, 0) for phase in MISSION_LLM_PHASES}
    return {**counts, "total": sum(counts.values())}


def file_integrity(data):
    """Re-hash an output file and compare it with the hash recorded when the
    tool wrote it."""
    path = Path((data or {}).get("path") or "")
    if not (data or {}).get("path"):
        return None
    if not path.is_file():
        return {"path": str(path), "exists": False, "intact": False}
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "exists": True, "sha256": current, "intact": current == data.get("sha256")}


def evidence_summary(record):
    if not record:
        return None
    return {
        key: record.get(key)
        for key in ("id", "step", "tool", "status", "trigger", "started_at", "finished_at",
                    "output", "data", "upstream_evidence", "stale_reason")
    } | {"file": file_integrity(record.get("data"))}


def build_receipt(mission):
    evidence = mission.get("evidence", [])
    by_id = {item.get("id"): item for item in evidence if item.get("id")}
    latest = latest_evidence(mission)
    verification = mission.get("verification") or {}
    results = verification.get("requirement_results", [])
    contract = mission.get("contract", {})

    def lineage(record):
        seen, pending, chain = set(), list((record or {}).get("upstream_evidence", {}).values()), []
        while pending:
            evidence_id = pending.pop(0)
            if evidence_id in seen or evidence_id not in by_id:
                continue
            seen.add(evidence_id)
            chain.append(evidence_summary(by_id[evidence_id]))
            pending.extend(by_id[evidence_id].get("upstream_evidence", {}).values())
        return chain

    if contract.get("requirement_specs"):
        result_by_id = {item.get("requirement_id"): item for item in results}
        requirements = []
        for spec in contract["requirement_specs"]:
            result = result_by_id.get(spec["id"], {})
            record = latest.get(trip_tools.REQUIREMENT_TASK[spec["type"]])
            requirements.append({
                "id": spec["id"],
                "type": spec["type"],
                "description": spec["description"],
                "parameters": spec["parameters"],
                "verifier": spec["verifier"],
                "status": result.get("status", "unverified"),
                "reason": result.get("reason"),
                "evidence": evidence_summary(record),
                "upstream_evidence": lineage(record),
            })
    else:
        requirements = [
            {key: item.get(key) for key in ("requirement", "status", "reason", "affected_task")}
            for item in results
        ]

    events = mission.get("events", [])
    valid, first_invalid = verify_event_chain(events)
    receipt = {
        "receipt_version": 1,
        "generated_at": now(),
        "mission": {key: mission.get(key) for key in ("id", "goal", "status", "created_at", "approval", "recovery_attempts")},
        "contract": {
            "objective": contract.get("objective"),
            "parameters": contract.get("parameters"),
            "constraints": contract.get("constraints"),
            "assumptions": contract.get("assumptions"),
            "amendments": contract.get("amendments", []),
            "compiler": contract.get("compiler"),
        },
        "requirements": requirements,
        "verification": {key: verification.get(key) for key in ("passed", "score")},
        "changes": mission.get("changes", []),
        "reexecution": mission.get("reexecution"),
        "recovery": {key: (mission.get("recovery") or {}).get(key) for key in ("status", "kind", "attempts", "reason")},
        "llm_calls": llm_summary(mission.get("llm_calls")),
        "event_log": events,
        "chain": {
            "algorithm": "sha256",
            "genesis_hash": GENESIS_HASH,
            "length": len(events),
            "final_hash": events[-1]["hash"] if events else GENESIS_HASH,
            "valid": valid,
            "first_invalid_sequence": first_invalid,
        },
    }
    # Freeze a deep copy so later mission activity (including the export's own
    # audit event) cannot alter the receipt after it is hashed.
    receipt = json.loads(json.dumps(receipt, ensure_ascii=False, default=str))
    canonical = json.dumps(receipt, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    receipt["receipt_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return receipt


@app.get("/mission/{mission_id}/receipt")
def mission_receipt(mission_id: str):

    mission = MISSIONS.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")
    receipt = build_receipt(mission)
    log(mission, "receipt_exported", "Mission receipt exported.", {
        "final_hash": receipt["chain"]["final_hash"],
        "receipt_sha256": receipt["receipt_sha256"],
    })
    return JSONResponse(
        receipt,
        headers={"Content-Disposition": f'attachment; filename="hades-receipt-{mission_id}.json"'},
    )


@app.get("/llm-calls")
def llm_calls():

    return {
        "totals": llm_summary(LLM_CALLS),
        "conversation": LLM_CALLS["conversation"],
        "missions": {mission_id: llm_summary(mission.get("llm_calls")) for mission_id, mission in MISSIONS.items()},
    }


# ============================================================
# SERVER
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
