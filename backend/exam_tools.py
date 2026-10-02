"""Exam-preparation tools for typed HADES missions.

Reuses the trip domain's shared machinery (task registry, output writer,
.ics escaping, ToolError) and registers its own tasks into it. Everything is
local: topics come from fixtures/syllabus.json and the calendar is a file.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import goal_compiler
import trip_tools
from trip_tools import ToolError, _ics_escape, _long_date, _parse_date, _require, _upstream, _write_output

MAX_SESSIONS = 6
WEEKDAY_SLOT = ("18:00", "20:00")
WEEKEND_SLOT = ("10:00", "12:00")
FINAL_REVISION = "Full revision and a timed past paper"
CHECKLIST_EXTRAS = [
    "Make a one-page sheet of key formulas and definitions",
    "Solve one past paper under timed conditions",
    "List doubts and clear them before the exam",
    "Pack exam essentials: admit card, ID, pens, calculator",
]

# Exam date changes re-run only the schedule and the calendar built from it;
# the syllabus and revision checklist depend on the subject alone.
TASKS = {
    "load_syllabus": {"title": "Load syllabus topics", "tool": "syllabus", "reads": ["subject"], "depends_on": []},
    "plan_study_sessions": {"title": "Plan study sessions", "tool": "study_planner", "reads": ["exam_date"], "depends_on": ["load_syllabus"]},
    "create_study_calendar": {"title": "Create study calendar", "tool": "study_calendar", "reads": ["subject"], "depends_on": ["plan_study_sessions"]},
    "build_revision_checklist": {"title": "Build revision checklist", "tool": "revision_checklist", "reads": ["subject"], "depends_on": ["load_syllabus"]},
}

REQUIREMENT_TASK = {
    "study_schedule": "plan_study_sessions",
    "study_calendar": "create_study_calendar",
    "revision_checklist": "build_revision_checklist",
}


def syllabus_topics(subject):
    """Topics for a subject and where they came from ("fixture"/"generic")."""
    syllabus = goal_compiler.load_syllabus()
    entry = syllabus["subjects"].get(subject)
    if entry:
        return list(entry["topics"]), "fixture"
    return list(syllabus["generic_topics"]), "generic"


def slot_for(day):
    return WEEKEND_SLOT if day.weekday() >= 5 else WEEKDAY_SLOT


def study_days(exam_date, today):
    """Days strictly between today and the exam (today itself only if the
    exam is tomorrow), keeping the MAX_SESSIONS days closest to the exam."""
    if exam_date <= today:
        raise ToolError(f"The exam on {exam_date.isoformat()} is not in the future; no study days remain.")
    days = [today + timedelta(days=offset) for offset in range(1, (exam_date - today).days)]
    if not days:
        days = [today]
    return days[-MAX_SESSIONS:]


# ============================================================
# TOOLS
# ============================================================

def load_syllabus(ctx):
    params = ctx["params"]
    _require(params, "subject")
    topics, source = syllabus_topics(params["subject"])
    data = {"subject": params["subject"], "topics": topics, "source": source}
    label = "local syllabus fixture" if source == "fixture" else "generic outline (subject not in fixture)"
    return f"{len(topics)} {params['subject']} topics from the {label}.", data


def plan_study_sessions(ctx):
    params = ctx["params"]
    _require(params, "exam_date")
    syllabus = _upstream(ctx, "load_syllabus")
    exam_date = _parse_date(params["exam_date"])
    today = ctx.get("today") or date.today()
    days = study_days(exam_date, today)
    topics = syllabus["topics"]

    revision_day = len(days) >= 3
    content_days = days[:-1] if revision_day else days
    content_days = content_days[-len(topics):] if len(content_days) > len(topics) else content_days
    used_days = content_days + ([days[-1]] if revision_day else [])

    # Split topics into contiguous, near-equal groups, one per content day.
    groups, start = [], 0
    for index in range(len(content_days)):
        size = len(topics) // len(content_days) + (1 if index < len(topics) % len(content_days) else 0)
        groups.append(topics[start:start + size])
        start += size
    if revision_day:
        groups.append([FINAL_REVISION])

    sessions = []
    for index, (day, group) in enumerate(zip(used_days, groups), 1):
        begin, end = slot_for(day)
        sessions.append({
            "index": index,
            "date": day.isoformat(),
            "start": begin,
            "end": end,
            "topics": group,
            "title": f"{syllabus['subject']} study: {', '.join(group)}",
        })
    data = {
        "subject": syllabus["subject"],
        "exam_date": exam_date.isoformat(),
        "planned_on": today.isoformat(),
        "sessions": sessions,
    }
    return f"{len(sessions)} sessions from {sessions[0]['date']} to {sessions[-1]['date']}, before the exam on {exam_date.isoformat()}.", data


def _ics_datetime(day, clock):
    return datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M").strftime("%Y%m%dT%H%M%S")


def create_study_calendar(ctx):
    schedule = _upstream(ctx, "plan_study_sessions")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HADES//Study Planner//EN", "CALSCALE:GREGORIAN"]
    for session in schedule["sessions"]:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ctx['mission_id']}-study-{session['index']}@hades.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_datetime(session['date'], session['start'])}",
            f"DTEND:{_ics_datetime(session['date'], session['end'])}",
            f"SUMMARY:{_ics_escape(session['title'])}",
            f"DESCRIPTION:{_ics_escape('Study session planned by HADES before the exam on ' + schedule['exam_date'] + '.')}",
            "END:VEVENT",
        ]
    lines += ["END:VCALENDAR", ""]
    written = _write_output(ctx["mission_id"], "study_plan.ics", "\r\n".join(lines), newline="")
    data = {**written, "events": len(schedule["sessions"]), "exam_date": schedule["exam_date"], "subject": schedule["subject"]}
    return f"Wrote {Path(written['path']).name} with {data['events']} study sessions.", data


def build_revision_checklist(ctx):
    params = ctx["params"]
    _require(params, "subject")
    syllabus = _upstream(ctx, "load_syllabus")
    items = [f"Revise {topic}" for topic in syllabus["topics"]] + CHECKLIST_EXTRAS
    title = f"{params['subject']} revision checklist"
    text = "\n".join([f"# {title}", ""] + [f"- [ ] {item}" for item in items]) + "\n"
    written = _write_output(ctx["mission_id"], "revision_checklist.md", text)
    data = {**written, "subject": params["subject"], "title": title, "items": items, "topics": syllabus["topics"], "source": syllabus["source"]}
    return f"{len(items)} checklist items for {params['subject']} saved to {Path(written['path']).name}.", data


TOOLS = {
    "syllabus": load_syllabus,
    "study_planner": plan_study_sessions,
    "study_calendar": create_study_calendar,
    "revision_checklist": build_revision_checklist,
}


def exam_summary(contract, evidence_by_task):
    params = contract.get("parameters", {})
    subject = params.get("subject") or "Exam"
    lines = [f"# {subject} exam prep", ""]
    if params.get("exam_date"):
        lines += [f"**Exam:** {_long_date(params['exam_date'])}", ""]
    schedule = evidence_by_task.get("plan_study_sessions")
    if schedule:
        lines.append("**Study schedule:**")
        for session in schedule["sessions"]:
            day = datetime.strptime(session["date"], "%Y-%m-%d").strftime("%a %d %b")
            lines.append(f"- {day}, {session['start']}–{session['end']}: {', '.join(session['topics'])}")
        lines.append("")
    calendar = evidence_by_task.get("create_study_calendar")
    if calendar:
        lines += [f"**Calendar ({calendar['events']} sessions):** `{calendar['path']}`", ""]
    checklist = evidence_by_task.get("build_revision_checklist")
    if checklist:
        lines += ["**Revision checklist:**"] + [f"- {item}" for item in checklist["items"]] + [""]
    return "\n".join(lines).strip()


trip_tools.register_domain("exam", TASKS, REQUIREMENT_TASK, TOOLS, exam_summary)
