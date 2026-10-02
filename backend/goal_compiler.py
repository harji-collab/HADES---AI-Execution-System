"""Typed goal decomposition for HADES.

The rule-based path below works with no LLM. An optional LLM proposal is only
accepted after `validate_decomposition` checks it against the requirement type
registry and against the facts the rules extracted from the goal text, so a
model can restructure a goal but can never invent a date, place or amount.
"""

import json
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

SYLLABUS_PATH = Path(__file__).resolve().parent / "fixtures" / "syllabus.json"


# ============================================================
# REGISTRIES
# ============================================================

# Requirement type -> verifier that judges it and the tool that produces its
# evidence. `required` parameters must be present for the requirement to run.
REQUIREMENT_TYPES = {
    "weather": {
        "verifier": "verify_weather",
        "tool": "weather",
        "required": ["destination", "trip_date"],
    },
    "packing_list": {
        "verifier": "verify_packing_list",
        "tool": "packing_list",
        "required": ["destination", "trip_date"],
    },
    "calendar_event": {
        "verifier": "verify_calendar_event",
        "tool": "calendar",
        "required": ["destination", "trip_date"],
    },
    "leave_email": {
        "verifier": "verify_leave_email",
        "tool": "leave_email",
        "required": ["trip_date", "recipient"],
    },
    "budget": {
        "verifier": "verify_budget",
        "tool": "fares",
        "required": ["max_budget", "currency", "trip_date"],
    },
    "study_schedule": {
        "verifier": "verify_study_schedule",
        "tool": "study_planner",
        "required": ["subject", "exam_date"],
    },
    "study_calendar": {
        "verifier": "verify_study_calendar",
        "tool": "study_calendar",
        "required": ["subject", "exam_date"],
    },
    "revision_checklist": {
        "verifier": "verify_revision_checklist",
        "tool": "revision_checklist",
        "required": ["subject"],
    },
}

# Requirement types per domain, in the order they are listed.
DOMAIN_TYPES = {
    "trip": ["weather", "packing_list", "calendar_event", "leave_email", "budget"],
    "exam": ["study_schedule", "study_calendar", "revision_checklist"],
}

# Order requirements are listed in, and the id each type receives.
TYPE_ORDER = [kind for kinds in DOMAIN_TYPES.values() for kind in kinds]
REQUIREMENT_IDS = {kind: f"req_{kind}" for kind in TYPE_ORDER}

# Small local gazetteer; coordinates are used by the weather tool.
DESTINATIONS = {
    "Bengaluru": {"aliases": ["bengaluru", "bangalore"], "lat": 12.97, "lon": 77.59},
    "Mumbai": {"aliases": ["mumbai", "bombay"], "lat": 19.08, "lon": 72.88},
    "Delhi": {"aliases": ["delhi", "new delhi"], "lat": 28.61, "lon": 77.21},
    "Chennai": {"aliases": ["chennai", "madras"], "lat": 13.08, "lon": 80.27},
    "Hyderabad": {"aliases": ["hyderabad"], "lat": 17.39, "lon": 78.49},
    "Pune": {"aliases": ["pune"], "lat": 18.52, "lon": 73.86},
    "Goa": {"aliases": ["goa"], "lat": 15.30, "lon": 74.12},
    "Mysuru": {"aliases": ["mysuru", "mysore"], "lat": 12.30, "lon": 76.64},
    "Kolkata": {"aliases": ["kolkata", "calcutta"], "lat": 22.57, "lon": 88.36},
}

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {
    name: index
    for index, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"),
            ("apr", "april"), ("may",), ("jun", "june"), ("jul", "july"),
            ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"),
            ("nov", "november"), ("dec", "december"),
        ],
        1,
    )
    for name in names
}

INTENT_PATTERNS = {
    "weather": r"\b(weather|forecast)\b",
    "packing_list": r"\b(packing list|pack list|what to pack|pack for)\b",
    "calendar_event": r"\b(calendar|\.ics)\b",
    "leave_email": (
        r"\b(leave|time[- ]off|vacation|out[- ]of[- ]office)\b[^.;:]{0,60}\b(e-?mail|mail)\b"
        r"|\b(e-?mail|mail)\b[^.;:]{0,60}\b(leave|time[- ]off|vacation|out[- ]of[- ]office)\b"
    ),
}

# "test" alone is too ambiguous ("write unit tests"), so it only counts as
# "my/the/a <subject> test".
EXAM_PATTERN = re.compile(
    r"\b(exams?|quiz|quizzes|midterms?|mid-terms?|finals|board exams?)\b"
    r"|\b(?:my|the|an?)\s+[a-z]+(?:\s+[a-z]+)?\s+test\b",
    re.I,
)
EXAM_ACTION_PATTERN = re.compile(r"\b(prepare|prep|ready|study|studying|revise|revision|plan|schedule)\b", re.I)

BUDGET_PATTERN = re.compile(
    r"\b(?:under|below|within|less than|at most|max(?:imum)?|up to|no more than"
    r"|not exceed(?:ing)?|budget(?: of)?|cap(?: of)?)\s*(?:of\s*|to\s*)?"
    r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?",
    re.I,
)


# ============================================================
# FACT EXTRACTION
# ============================================================

def resolve_weekday(name, today):
    """Next occurrence strictly after today, so "Friday" said on a Friday
    means the following week."""
    ahead = (WEEKDAYS.index(name) - today.weekday()) % 7
    return today + timedelta(days=ahead or 7)


def extract_date(text, today):
    lowered = text.casefold()

    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lowered)
    if match:
        try:
            return date(*map(int, match.groups())), match.group(0)
        except ValueError:
            pass

    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    for pattern, day_group, month_group in (
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})\b", 1, 2),
        (rf"\b({month_names})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", 2, 1),
    ):
        match = re.search(pattern, lowered)
        if match:
            try:
                found = date(today.year, MONTHS[match.group(month_group)], int(match.group(day_group)))
            except ValueError:
                continue
            if found < today:
                found = found.replace(year=today.year + 1)
            return found, match.group(0)

    if re.search(r"\bday after tomorrow\b", lowered):
        return today + timedelta(days=2), "day after tomorrow"
    if re.search(r"\btomorrow\b", lowered):
        return today + timedelta(days=1), "tomorrow"
    if re.search(r"\btoday\b", lowered):
        return today, "today"

    match = re.search(rf"\b({'|'.join(WEEKDAYS)})\b", lowered)
    if match:
        return resolve_weekday(match.group(1), today), match.group(1)

    return None, None


def extract_destination(text):
    lowered = text.casefold()
    for name, info in DESTINATIONS.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in info["aliases"]):
            return name

    match = re.search(r"\b(?:trip|travel|flight|journey)\s+to\s+([A-Z][a-zA-Z]+)", text) or re.search(
        r"\bmy\s+([A-Z][a-zA-Z]+)\s+(?:trip|visit|travel)\b", text
    )
    # "trip to Sunday" names a day, not a place.
    if not match or match.group(1).casefold() in set(WEEKDAYS) | set(MONTHS) | {"today", "tomorrow"}:
        return None
    return match.group(1)


def extract_budget(text):
    match = BUDGET_PATTERN.search(text)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    if match.group(2):
        amount *= 1000
    if amount <= 0:
        return None
    return int(amount) if amount.is_integer() else amount


def extract_recipient(text):
    match = re.search(r"\bto\s+my\s+(manager|boss|team lead|lead|supervisor|hr)\b", text, re.I)
    return match.group(1).lower() if match else "manager"


@lru_cache(maxsize=1)
def load_syllabus():
    with open(SYLLABUS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def canonical_subject(text):
    """Map a subject mention to its syllabus name, or title-case it."""
    lowered = str(text or "").casefold().strip()
    if not lowered:
        return None
    for name, info in load_syllabus()["subjects"].items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in info["aliases"]):
            return name
    return lowered.title()


def extract_subject(text):
    for name, info in load_syllabus()["subjects"].items():
        if any(re.search(rf"\b{re.escape(alias)}\b", text.casefold()) for alias in info["aliases"]):
            return name
    match = re.search(
        r"\b(?:my|the|for|an?)\s+([a-z][a-z ]{1,30}?)\s+(?:exams?|tests?|quiz|midterms?|finals?)\b",
        text,
        re.I,
    )
    if not match:
        return None
    filler = {"my", "the", "a", "an", "for", "upcoming", "next", "big", "final"}
    words = [word for word in match.group(1).split() if word.casefold() not in filler]
    return canonical_subject(" ".join(words)) if words else None


def extract_facts(goal, today):
    found_date, date_text = extract_date(goal, today)
    iso = found_date.isoformat() if found_date else None
    return {
        "destination": extract_destination(goal),
        "trip_date": iso,
        "exam_date": iso,
        "date_text": date_text,
        "max_budget": extract_budget(goal),
        "currency": "INR",
        "recipient": extract_recipient(goal),
        "subject": extract_subject(goal),
    }


def is_exam_goal(goal):
    return bool(EXAM_PATTERN.search(goal) and EXAM_ACTION_PATTERN.search(goal))


def detect_domain(goal):
    """Return (domain, requirement types) or (None, [])."""
    if is_exam_goal(goal):
        return "exam", list(DOMAIN_TYPES["exam"])
    kinds = detect_intents(goal)
    return ("trip", kinds) if kinds else (None, [])


def detect_intents(goal):
    lowered = goal.casefold()
    intents = [kind for kind, pattern in INTENT_PATTERNS.items() if re.search(pattern, lowered)]
    # A cost limit is a constraint on a task-bearing goal; on its own (for
    # example a funds transfer amount) it does not make a typed contract.
    if intents and extract_budget(goal) is not None:
        intents.append("budget")
    return [kind for kind in DOMAIN_TYPES["trip"] if kind in intents]


# ============================================================
# REQUIREMENT CONSTRUCTION
# ============================================================

def date_label(iso):
    if not iso:
        return "an unresolved date"
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%a %d %b %Y")


def describe(kind, params):
    place = params.get("destination") or "the destination"
    when = date_label(params.get("trip_date"))
    if kind == "weather":
        return f"Check the weather forecast for {place} on {when}"
    if kind == "packing_list":
        return f"Build a packing list for {place} consistent with the forecast"
    if kind == "calendar_event":
        return f"Add the {place} trip on {when} to the calendar"
    if kind == "leave_email":
        return f"Draft a leave email to my {params.get('recipient') or 'manager'} for {when}"
    if kind == "budget":
        amount = params.get("max_budget")
        return f"Keep total trip cost under ₹{amount:,}" if amount is not None else "Keep total trip cost within budget"
    subject = params.get("subject") or "the subject"
    exam = date_label(params.get("exam_date"))
    if kind == "study_schedule":
        return f"Build a {subject} study schedule with sessions before the exam on {exam}"
    if kind == "study_calendar":
        return f"Add every {subject} study session to the calendar"
    if kind == "revision_checklist":
        return f"Create a {subject} revision checklist"
    return kind


def requirement_dependencies(kind, kinds):
    if kind == "packing_list" and "weather" in kinds:
        return [REQUIREMENT_IDS["weather"]]
    if kind == "study_calendar" and "study_schedule" in kinds:
        return [REQUIREMENT_IDS["study_schedule"]]
    return []


def build_requirement(kind, facts, kinds, depends_on=None):
    spec = REQUIREMENT_TYPES[kind]
    params = {key: facts.get(key) for key in spec["required"]}
    return {
        "id": REQUIREMENT_IDS[kind],
        "type": kind,
        "description": describe(kind, params),
        "parameters": params,
        "verifier": spec["verifier"],
        "tool": spec["tool"],
        "depends_on": requirement_dependencies(kind, kinds) if depends_on is None else depends_on,
        "unresolved": [key for key in spec["required"] if params.get(key) in (None, "")],
    }


def decompose_goal(goal, today=None):
    """Rule-based decomposition. Returns None when the goal has no supported
    typed intents, so the caller keeps the legacy free-text contract."""
    today = today or date.today()
    domain, kinds = detect_domain(goal)
    if not kinds:
        return None
    facts = extract_facts(goal, today)
    return {
        "domain": domain,
        "facts": facts,
        "requirements": [build_requirement(kind, facts, kinds) for kind in kinds],
    }


# ============================================================
# CONTRACT CHANGES
# ============================================================

CHANGEABLE = ("trip_date", "destination", "max_budget", "travel_mode", "exam_date", "subject")
DATE_KEYS = ("trip_date", "exam_date")
TRAVEL_MODES = ("train", "bus")


def parse_change_text(text, today=None, date_key="trip_date"):
    """Extract parameter changes from a chat message such as
    "trip moved to Sunday", "exam moved to Wednesday" or "switch to the
    night bus". date_key names the contract's date parameter."""
    today = today or date.today()
    changes = {}
    found, _ = extract_date(text, today)
    if found:
        changes[date_key] = found.isoformat()
    lowered = text.casefold()
    for name, info in DESTINATIONS.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in info["aliases"]):
            changes["destination"] = name
            break
    budget = extract_budget(text)
    if budget is not None:
        changes["max_budget"] = budget
    mode = re.search(r"\b(train|bus)\b", lowered)
    if mode:
        changes["travel_mode"] = mode.group(1)
    return changes


def normalize_changes(changes, today=None):
    """Validate structured changes such as {"trip_date": "Sunday"}. Returns
    normalized values or raises ValueError."""
    today = today or date.today()
    if not isinstance(changes, dict) or not changes:
        raise ValueError("No changes were provided.")
    unknown = set(changes) - set(CHANGEABLE)
    if unknown:
        raise ValueError(f"Cannot change {', '.join(sorted(unknown))}; changeable: {', '.join(CHANGEABLE)}.")

    normalized = {}
    for key, value in changes.items():
        if key == "subject":
            subject = canonical_subject(value) if isinstance(value, str) else None
            if not subject:
                raise ValueError(f"Could not understand the subject {value!r}.")
            normalized[key] = subject
        elif key in DATE_KEYS:
            text = str(value).strip()
            try:
                normalized[key] = datetime.strptime(text, "%Y-%m-%d").date().isoformat()
            except ValueError:
                found, _ = extract_date(text, today)
                if not found:
                    raise ValueError(f"Could not understand the date {value!r}.")
                normalized[key] = found.isoformat()
        elif key == "destination":
            name = value if isinstance(value, str) and value in DESTINATIONS else extract_destination(str(value))
            if name not in DESTINATIONS:
                raise ValueError(f"{value!r} is not a supported destination.")
            normalized[key] = name
        elif key == "max_budget":
            amount = value if isinstance(value, (int, float)) and not isinstance(value, bool) else extract_budget(f"budget {value}")
            if amount is None or amount <= 0:
                raise ValueError(f"Could not understand the budget {value!r}.")
            normalized[key] = int(amount) if float(amount).is_integer() else amount
        elif key == "travel_mode":
            if str(value).casefold() not in TRAVEL_MODES:
                raise ValueError(f"travel_mode must be one of {', '.join(TRAVEL_MODES)}.")
            normalized[key] = str(value).casefold()
    return normalized


def refresh_requirement(spec, parameters):
    """Copy updated contract parameters into a requirement and rebuild its
    description."""
    for key in spec["parameters"]:
        if key in parameters:
            spec["parameters"][key] = parameters[key]
    spec["description"] = describe(spec["type"], spec["parameters"])
    spec["unresolved"] = [key for key, value in spec["parameters"].items() if value in (None, "")]
    return spec


# ============================================================
# INPUT CLASSIFICATION
# ============================================================

INPUT_KINDS = ("GOAL", "QUESTION", "CHAT")

EXAMPLE_GOALS = [
    "Get me ready for my Bengaluru trip on Friday: check the weather, build a packing list, "
    "add it to my calendar, draft a leave email to my manager, keep total cost under ₹4,000",
    "Prepare me for my physics exam on Monday",
]

GREETING = re.compile(
    r"^(hi+|hello+|hey+|hiya|yo|hola|namaste|good (morning|afternoon|evening|night)|thanks|thank you|thx|"
    r"ok(ay)?|cool|nice|great|awesome|bye|goodbye|see you|how are you|how's it going|what'?s up|sup|lol|haha)\b",
    re.I,
)
QUESTION_START = re.compile(
    r"^(what|who|whom|whose|when|where|why|how|which|is|are|am|was|were|do|does|did|can|could|"
    r"would|will|should|shall|may|might|have|has)\b",
    re.I,
)
POLITE_REQUEST = re.compile(r"^(please\b|(can|could|would|will) you\b)", re.I)
ACTION_VERB = re.compile(
    r"\b(create|make|build|prepare|prep|plan|draft|write|research|generate|add|schedule|book|get me|"
    r"help me|organi[sz]e|analy[sz]e|summari[sz]e|compare|find|list|transfer|send|pay|buy|design|"
    r"set up|setup|remind|check|keep|track|study|revise|review|compile|produce|deliver|inspect|scan|"
    r"audit|update|fix|cancel|arrange|calculate|draw up)\b",
    re.I,
)


def classify_input(text):
    """Rule-based GOAL / QUESTION / CHAT classification.

    Anything HADES can decompose is a goal. Otherwise greetings are chat,
    questions are questions, and imperative requests are goals. Unclear
    longer text defaults to GOAL so existing free-text missions still run.
    Returns (kind, reason)."""
    stripped = (text or "").strip()
    words = re.findall(r"[\w'₹]+", stripped)
    if not words:
        return "CHAT", "Empty message."
    if decompose_goal(stripped) is not None:
        return "GOAL", "Matches a supported goal domain."
    has_action = bool(ACTION_VERB.search(stripped))
    if GREETING.match(stripped) and len(words) <= 6 and not has_action:
        return "CHAT", "Greeting or small talk."
    if POLITE_REQUEST.match(stripped) and has_action:
        return "GOAL", "Polite request to do something."
    if stripped.endswith("?") or QUESTION_START.match(stripped):
        return "QUESTION", "Phrased as a question with no task to execute."
    if has_action:
        return "GOAL", "Imperative request."
    if len(words) <= 4:
        return "CHAT", "Short message with no actionable intent."
    return "GOAL", "Treated as a goal by default."


def classify_prompt(text):
    return f"""
Classify the user's message for an agent that only executes goals (tasks
with deliverables). Kinds: GOAL (asks for something to be done), QUESTION
(asks for information), CHAT (greeting or small talk).
If it is a QUESTION or CHAT, also give a one-line reply (max 25 words).

MESSAGE:
{text}

Return JSON only: {{"kind": "GOAL|QUESTION|CHAT", "answer": "<one line or empty>"}}
"""


def validate_classification(data):
    """Validate an LLM classification. Returns (kind, answer) or raises."""
    if not isinstance(data, dict) or data.get("kind") not in INPUT_KINDS:
        raise ValueError("Classification must have kind GOAL, QUESTION or CHAT.")
    answer = data.get("answer") if isinstance(data.get("answer"), str) else ""
    answer = " ".join(answer.split())[:300]
    return data["kind"], answer if data["kind"] != "GOAL" else ""


# ============================================================
# LLM PROPOSAL VALIDATION
# ============================================================

def llm_prompt(goal, today=None):
    today = today or date.today()
    types_text = "\n".join(
        f'- "{kind}": verifier "{spec["verifier"]}", parameters {spec["required"]}'
        for kind, spec in REQUIREMENT_TYPES.items()
    )
    return f"""
Decompose this goal into typed requirements. Today is {today.isoformat()}.

GOAL:
{goal}

Allowed requirement types (use no others):
{types_text}

Return JSON only:
{{"requirements": [{{"id": "req_<type>", "type": "<type>", "verifier": "<verifier>",
  "parameters": {{...}}, "depends_on": ["<requirement id>"]}}]}}

Rules: trip_date is YYYY-MM-DD; max_budget is a number; currency is "INR".
Only use values stated in the goal. Omit types the goal does not ask for.
"""


def _has_cycle(requirements):
    graph = {item["id"]: item.get("depends_on", []) for item in requirements}
    state = {}

    def visit(node):
        if state.get(node) == "visiting":
            return True
        if state.get(node) == "done":
            return False
        state[node] = "visiting"
        if any(visit(dep) for dep in graph.get(node, [])):
            return True
        state[node] = "done"
        return False

    return any(visit(node) for node in graph)


def validate_decomposition(data, goal, rule_result, today=None):
    """Validate an LLM proposal. Returns typed requirements built from
    registry data, or raises ValueError explaining the rejection."""
    today = today or date.today()
    if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        raise ValueError("Proposal is not an object with a requirements list.")

    items = data["requirements"]
    if not 1 <= len(items) <= len(REQUIREMENT_TYPES):
        raise ValueError("Proposal has an invalid number of requirements.")

    facts = dict(rule_result["facts"]) if rule_result else extract_facts(goal, today)
    lowered_goal = goal.casefold()
    seen_types = set()
    proposed_ids = set()

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Every requirement must be an object.")
        kind = item.get("type")
        if kind not in REQUIREMENT_TYPES:
            raise ValueError(f"Unknown requirement type {kind!r}.")
        if kind in seen_types:
            raise ValueError(f"Duplicate requirement type {kind!r}.")
        seen_types.add(kind)
        if item.get("id") != REQUIREMENT_IDS[kind]:
            raise ValueError(f"Requirement id for {kind!r} must be {REQUIREMENT_IDS[kind]!r}.")
        proposed_ids.add(item["id"])
        if item.get("verifier") != REQUIREMENT_TYPES[kind]["verifier"]:
            raise ValueError(f"Verifier for {kind!r} must be {REQUIREMENT_TYPES[kind]['verifier']!r}.")
        if not isinstance(item.get("parameters"), dict):
            raise ValueError(f"Parameters for {kind!r} must be an object.")
        if not isinstance(item.get("depends_on", []), list):
            raise ValueError(f"depends_on for {kind!r} must be a list.")

        params = item["parameters"]
        for key in REQUIREMENT_TYPES[kind]["required"]:
            value = params.get(key)
            if value in (None, ""):
                continue
            if key == "trip_date":
                try:
                    datetime.strptime(str(value), "%Y-%m-%d")
                except ValueError:
                    raise ValueError("trip_date must be YYYY-MM-DD.")
            if key == "max_budget" and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
                raise ValueError("max_budget must be a positive number.")
            if key == "currency" and value != "INR":
                raise ValueError("currency must be INR.")
            # The model may restructure the goal but never introduce facts.
            known = facts.get(key)
            if known is not None and key != "recipient" and value != known:
                raise ValueError(f"{key}={value!r} contradicts the goal text ({known!r}).")
            if known is None and key in {"trip_date", "exam_date", "max_budget", "destination", "subject"}:
                # Only place/subject names that literally appear in the goal
                # may be filled in; dates and amounts must come from the rules.
                if key not in {"destination", "subject"} or str(value).casefold() not in lowered_goal:
                    raise ValueError(f"{key}={value!r} is not stated in the goal.")
                facts[key] = value

    for item in items:
        unknown = set(item.get("depends_on", [])) - proposed_ids
        if unknown:
            raise ValueError(f"Unknown dependencies: {sorted(unknown)}.")
    if _has_cycle(items):
        raise ValueError("Requirement dependencies contain a cycle.")

    rule_kinds = {item["type"] for item in (rule_result or {}).get("requirements", [])}
    if rule_kinds - seen_types:
        raise ValueError(f"Proposal omits requested requirements: {sorted(rule_kinds - seen_types)}.")

    kinds = [kind for kind in TYPE_ORDER if kind in seen_types]
    domains = {domain for domain, types in DOMAIN_TYPES.items() if set(kinds) & set(types)}
    if len(domains) != 1:
        raise ValueError("Proposal mixes requirement types from different domains.")
    by_type = {item["type"]: item for item in items}
    return {
        "domain": domains.pop(),
        "facts": facts,
        "requirements": [
            build_requirement(kind, facts, kinds, depends_on=list(by_type[kind].get("depends_on", [])))
            for kind in kinds
        ],
    }
