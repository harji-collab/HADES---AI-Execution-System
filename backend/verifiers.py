"""Independent verifiers for typed HADES requirements.

A verifier judges the real artifact (the file on disk, the cached forecast,
the fare fixture), never the producing tool's own success flag or totals.
Each returns (passed, human-readable reason).
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import exam_tools
import trip_tools
from goal_compiler import DESTINATIONS


def _long_date(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%A, %d %B %Y")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _usable(record):
    """Reject evidence that is missing or explicitly stale before inspecting it."""
    if not record:
        return False, "No evidence was recorded."
    if record.get("status") == "stale":
        return False, f"Evidence {record.get('id')} is stale: {record.get('stale_reason') or 'an input changed'}."
    if record.get("data") is None:
        return False, record.get("output") or "The tool produced no inspectable result."
    return True, ""


def _latest_complete(latest, task_id):
    record = latest.get(task_id)
    return record if record and record.get("status") == "complete" and record.get("data") is not None else None


# ============================================================
# WEATHER
# ============================================================

def verify_weather(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    data = record["data"]
    params = spec["parameters"]

    if data.get("date") != params.get("trip_date"):
        return False, f"Forecast is for {data.get('date')}, but the trip is on {params.get('trip_date')}."
    place = DESTINATIONS.get(params.get("destination"))
    if not place or (data.get("latitude"), data.get("longitude")) != (place["lat"], place["lon"]):
        return False, f"Forecast coordinates do not match {params.get('destination')}."

    rain = data.get("precipitation_probability_max")
    tmax, tmin = data.get("temperature_max"), data.get("temperature_min")
    if not (_number(rain) and 0 <= rain <= 100):
        return False, f"Rain probability {rain!r} is not a valid percentage."
    if not (_number(tmax) and _number(tmin) and -30 <= tmin <= tmax <= 55):
        return False, f"Temperatures {tmin!r}-{tmax!r} °C are not plausible."

    # Provenance: every accepted forecast (live or offline) must exist in the
    # local cache with the same values, so the reading can be re-checked.
    key = f"{data['latitude']},{data['longitude']},{data['date']}"
    try:
        cached = json.loads((trip_tools.CACHE_DIR / "weather.json").read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError):
        cached = None
    if not cached:
        return False, f"No cached Open-Meteo record backs the forecast for {data['date']}."
    for field in ("precipitation_probability_max", "temperature_max", "temperature_min", "weather_code"):
        if cached.get(field) != data.get(field):
            return False, f"Forecast {field} differs from the cached Open-Meteo record."

    return True, (
        f"Open-Meteo forecast for {params['destination']} on {_long_date(data['date'])}: "
        f"rain {rain}%, {tmin}-{tmax} °C ({data.get('source')}, fetched {cached.get('fetched_at', '?')[:16]})."
    )


# ============================================================
# PACKING LIST
# ============================================================

def verify_packing_list(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    weather_record = _latest_complete(latest, "fetch_weather")
    if not weather_record:
        return False, "No valid weather evidence to check the packing list against."
    if record.get("upstream_evidence", {}).get("fetch_weather") != weather_record.get("id"):
        return False, f"Packing list was built from older weather evidence, not {weather_record.get('id')}."

    weather = weather_record["data"]
    if weather.get("date") != spec["parameters"].get("trip_date"):
        return False, f"Weather evidence is for {weather.get('date')}, not the trip date."

    items = {entry.get("item") for entry in record["data"].get("items", []) if isinstance(entry, dict)}
    missing_base = [item for item in trip_tools.BASE_PACKING if item not in items]
    if missing_base:
        return False, f"Missing essentials: {', '.join(missing_base)}."

    rain = weather["precipitation_probability_max"]
    expected = {item for item, _ in trip_tools.packing_rules(weather)}
    missing = sorted(expected - items)
    if missing:
        return False, f"Forecast (rain {rain}%) requires {', '.join(missing)}, which the list lacks."
    rain_gear = {"Umbrella", "Raincoat"} & items
    if rain <= trip_tools.RAIN_THRESHOLD and rain_gear:
        return False, f"Rain chance is only {rain}%, yet the list includes {', '.join(sorted(rain_gear))}."

    weather_items = sorted(expected)
    return True, (
        f"{len(items)} items, consistent with rain {rain}%"
        + (f" (includes {', '.join(weather_items)})." if weather_items else "; no rain gear needed.")
    )


# ============================================================
# CALENDAR
# ============================================================

def parse_ics(text):
    """Minimal RFC 5545 reader: unfolds lines and returns the VEVENT
    properties, keyed by name with parameters stripped."""
    lines = re.sub(r"\r?\n[ \t]", "", text).splitlines()
    if not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise ValueError("File is not wrapped in BEGIN/END:VCALENDAR.")
    if "VERSION:2.0" not in lines:
        raise ValueError("VERSION:2.0 is missing.")
    if lines.count("BEGIN:VEVENT") != 1 or lines.count("END:VEVENT") != 1:
        raise ValueError("Expected exactly one VEVENT.")
    start, end = lines.index("BEGIN:VEVENT"), lines.index("END:VEVENT")
    if start > end:
        raise ValueError("VEVENT is malformed.")
    props = {}
    for line in lines[start + 1:end]:
        name_part, _, value = line.partition(":")
        props[name_part.split(";")[0].upper()] = value
    return props


def _ics_date(value):
    return datetime.strptime(value[:8], "%Y%m%d").date()


def verify_calendar_event(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    path = Path(record["data"].get("path", ""))
    if not path.is_file():
        return False, f"Calendar file {path.name or '(none)'} does not exist."
    try:
        props = parse_ics(path.read_text(encoding="utf-8"))
        for required in ("UID", "DTSTAMP", "DTSTART", "SUMMARY"):
            if required not in props:
                raise ValueError(f"{required} is missing.")
        start = _ics_date(props["DTSTART"])
        end = _ics_date(props["DTEND"]) if "DTEND" in props else start + timedelta(days=1)
    except (OSError, ValueError) as exc:
        return False, f"{path.name} is not a valid calendar file: {exc}"

    trip_date = spec["parameters"].get("trip_date")
    if start.isoformat() != trip_date:
        return False, f"{path.name} starts on {start.isoformat()}, but the trip is on {trip_date}."
    if end <= start:
        return False, f"{path.name} ends before it starts."
    destination = spec["parameters"].get("destination") or ""
    if destination.casefold() not in (props["SUMMARY"] + props.get("LOCATION", "")).casefold():
        return False, f"{path.name} does not mention {destination}."
    return True, f"Parsed {path.name}: one event on {_long_date(trip_date)} for {destination}."


# ============================================================
# LEAVE EMAIL
# ============================================================

LONG_DATE = re.compile(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), \d{2} [A-Z][a-z]+ \d{4}\b")


def verify_leave_email(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    path = Path(record["data"].get("path", ""))
    if not path.is_file():
        return False, f"Email draft {path.name or '(none)'} does not exist."
    text = path.read_text(encoding="utf-8")

    if not text.startswith("DRAFT - NOT SENT"):
        return False, f"{path.name} is not marked as an unsent draft."
    if not re.search(r"(?m)^To: \S", text) or not re.search(r"(?m)^Subject: \S", text):
        return False, f"{path.name} lacks a To or Subject line."

    trip_date = spec["parameters"].get("trip_date")
    expected = _long_date(trip_date)
    mentioned = {match.group(0) for match in LONG_DATE.finditer(text)}
    if expected not in mentioned:
        return False, f"{path.name} does not mention the trip date ({expected})."
    if mentioned - {expected}:
        return False, f"{path.name} also mentions {', '.join(sorted(mentioned - {expected}))}, which is not the trip date."
    destination = contract.get("parameters", {}).get("destination")
    if destination and destination not in text:
        return False, f"{path.name} does not mention {destination}."
    return True, f"{path.name} exists, is an unsent draft, and names {expected}."


# ============================================================
# BUDGET
# ============================================================

def verify_budget(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    params = spec["parameters"]
    limit = params.get("max_budget")
    trip_date = params.get("trip_date")
    mode = contract.get("parameters", {}).get("travel_mode") or "train"
    destination = contract.get("parameters", {}).get("destination")
    if not _number(limit):
        return False, "The contract has no numeric budget limit."

    # Re-derive the cost from the fare fixture instead of trusting the tool.
    try:
        _, route, weekday, options = trip_tools.fare_options(destination, datetime.strptime(trip_date, "%Y-%m-%d").date())
    except (trip_tools.ToolError, ValueError, TypeError) as exc:
        return False, f"Cannot re-derive fares: {exc}"
    option = next((item for item in options if item["mode"] == mode), None)
    if not option:
        return False, f"No {mode} fare exists for {weekday.title()} in the fixture."
    expected_total = option["outbound"] + option["return"] + sum(item["amount"] for item in route["local_expenses"])

    data = record["data"]
    items = data.get("line_items") or []
    if not all(isinstance(item, dict) and _number(item.get("amount")) for item in items):
        return False, "Budget line items are malformed."
    resummed = sum(item["amount"] for item in items)
    if resummed != data.get("total"):
        return False, f"Line items sum to ₹{resummed:,}, but the tool reported ₹{data.get('total')!r}."
    if resummed != expected_total:
        return False, f"Recorded cost ₹{resummed:,} does not match the {weekday.title()} {mode} fixture total ₹{expected_total:,}."

    breakdown = f"{weekday.title()} {mode} ₹{option['outbound'] + option['return']:,} + local ₹{expected_total - option['outbound'] - option['return']:,}"
    if expected_total > limit:
        return False, f"Total ₹{expected_total:,} ({breakdown}) exceeds the ₹{limit:,} limit by ₹{expected_total - limit:,}."
    return True, f"Total ₹{expected_total:,} ({breakdown}) is within the ₹{limit:,} limit."


# ============================================================
# EXAM PREPARATION
# ============================================================

def _session_bounds(session):
    start = datetime.strptime(f"{session['date']} {session['start']}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{session['date']} {session['end']}", "%Y-%m-%d %H:%M")
    return start, end


def verify_study_schedule(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    exam_date = spec["parameters"].get("exam_date")
    sessions = record["data"].get("sessions") or []
    if not sessions:
        return False, "The schedule has no study sessions."
    try:
        bounds = sorted((_session_bounds(session) + (session,) for session in sessions), key=lambda item: item[0])
    except (KeyError, TypeError, ValueError):
        return False, "A study session has a malformed date or time."

    exam_day = datetime.strptime(exam_date, "%Y-%m-%d")
    for start, end, session in bounds:
        if end <= start:
            return False, f"Session {session.get('index')} ends before it starts."
        if start.date() >= exam_day.date():
            return False, f"Session on {start.date().isoformat()} is not before the exam on {exam_date}."
    for (_, previous_end, previous), (next_start, _, following) in zip(bounds, bounds[1:]):
        if next_start < previous_end:
            return False, f"Sessions {previous.get('index')} and {following.get('index')} overlap."

    # Every syllabus topic for the subject must be scheduled somewhere.
    expected, _ = exam_tools.syllabus_topics(spec["parameters"].get("subject"))
    covered = {topic for session in sessions for topic in session.get("topics", [])}
    missing = [topic for topic in expected if topic not in covered]
    if missing:
        return False, f"No session covers: {', '.join(missing)}."

    first, last = bounds[0][0], bounds[-1][1]
    return True, (
        f"{len(sessions)} non-overlapping sessions from {first:%a %d %b} to {last:%a %d %b}, "
        f"all before the exam on {_long_date(exam_date)}, covering all {len(expected)} topics."
    )


def parse_ics_events(text):
    """Unfold an iCalendar file and return its VEVENTs as property dicts."""
    lines = re.sub(r"\r?\n[ \t]", "", text).splitlines()
    if not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise ValueError("File is not wrapped in BEGIN/END:VCALENDAR.")
    if "VERSION:2.0" not in lines:
        raise ValueError("VERSION:2.0 is missing.")
    events, current = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            if current is not None:
                raise ValueError("Nested VEVENT.")
            current = {}
        elif line == "END:VEVENT":
            if current is None:
                raise ValueError("END:VEVENT without BEGIN.")
            events.append(current)
            current = None
        elif current is not None:
            name, _, value = line.partition(":")
            current[name.split(";")[0].upper()] = value
    if current is not None:
        raise ValueError("Unterminated VEVENT.")
    return events


def verify_study_calendar(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    schedule_record = _latest_complete(latest, "plan_study_sessions")
    if not schedule_record:
        return False, "No valid study schedule to check the calendar against."
    if record.get("upstream_evidence", {}).get("plan_study_sessions") != schedule_record.get("id"):
        return False, f"Calendar was built from an older schedule, not {schedule_record.get('id')}."

    path = Path(record["data"].get("path", ""))
    if not path.is_file():
        return False, f"Calendar file {path.name or '(none)'} does not exist."
    try:
        events = parse_ics_events(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"{path.name} is not a valid calendar file: {exc}"

    in_file = {(event.get("DTSTART", ""), event.get("DTEND", "")) for event in events}
    expected = {
        (start.strftime("%Y%m%dT%H%M%S"), end.strftime("%Y%m%dT%H%M%S"))
        for start, end in (_session_bounds(session) for session in schedule_record["data"]["sessions"])
    }
    missing = expected - in_file
    if missing:
        return False, f"{path.name} is missing {len(missing)} of {len(expected)} sessions."
    extra = in_file - expected
    if extra:
        return False, f"{path.name} has {len(extra)} event(s) that are not in the schedule."
    exam_date = spec["parameters"].get("exam_date", "").replace("-", "")
    if any(start[:8] >= exam_date for start, _ in in_file):
        return False, f"{path.name} has a session on or after the exam date."
    return True, f"Parsed {path.name}: all {len(expected)} sessions present, none on or after the exam."


def verify_revision_checklist(spec, record, latest, contract):
    ok, reason = _usable(record)
    if not ok:
        return False, reason
    subject = spec["parameters"].get("subject")
    path = Path(record["data"].get("path", ""))
    if not path.is_file():
        return False, f"Checklist file {path.name or '(none)'} does not exist."
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0] if lines else ""
    items = [line[6:].strip() for line in lines if line.startswith("- [ ] ")]
    if not items:
        return False, f"{path.name} has no checklist items."
    if not subject or subject.casefold() not in title.casefold():
        return False, f"{path.name} is titled {title!r}, which does not name {subject}."

    expected, source = exam_tools.syllabus_topics(subject)
    missing = [topic for topic in expected if f"Revise {topic}" not in items]
    if missing:
        return False, f"Checklist does not cover {subject} topics: {', '.join(missing)}."
    basis = "the syllabus fixture" if source == "fixture" else "the generic outline (subject not in fixture)"
    return True, f"{path.name}: {len(items)} items, titled for {subject}, covering all {len(expected)} topics from {basis}."


VERIFIERS = {
    "verify_weather": verify_weather,
    "verify_packing_list": verify_packing_list,
    "verify_calendar_event": verify_calendar_event,
    "verify_leave_email": verify_leave_email,
    "verify_budget": verify_budget,
    "verify_study_schedule": verify_study_schedule,
    "verify_study_calendar": verify_study_calendar,
    "verify_revision_checklist": verify_revision_checklist,
}
