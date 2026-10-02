"""Local-first trip tools for typed HADES missions.

Every tool is free: weather comes from Open-Meteo (no key) with a local JSON
cache fallback, fares come from a local fixture, and calendar/email outputs are
files written to the outputs folder. Nothing is ever sent anywhere.
"""

import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from goal_compiler import DESTINATIONS

BACKEND_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = BACKEND_DIR / "fixtures"
OUTPUT_DIR = Path(os.getenv("HADES_OUTPUT_DIR", BACKEND_DIR / "outputs")).resolve()
CACHE_DIR = Path(os.getenv("HADES_CACHE_DIR", BACKEND_DIR / "cache")).resolve()

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16
HTTP_TIMEOUT_SECONDS = 8
RAIN_THRESHOLD = 50

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 80: "Rain showers",
    81: "Heavy rain showers", 82: "Violent rain showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}

BASE_PACKING = [
    "ID proof (Aadhaar or driving licence)",
    "Travel tickets",
    "Phone and charger",
    "Power bank",
    "Toiletries",
    "Clothes for the trip",
    "Regular medicines",
]


class ToolError(Exception):
    """A tool could not produce real output; the message is shown verbatim."""


# ============================================================
# TASK GRAPH
# ============================================================

# Each task lists the contract parameters it reads and the tasks whose
# evidence it consumes. Tasks that read no date-bearing parameter survive a
# trip date change untouched.
TASKS = {
    "resolve_destination": {"title": "Resolve destination", "tool": "destination", "reads": ["destination"], "depends_on": []},
    "fetch_weather": {"title": "Fetch weather forecast", "tool": "weather", "reads": ["trip_date"], "depends_on": ["resolve_destination"]},
    "base_packing": {"title": "Load packing essentials", "tool": "packing_base", "reads": [], "depends_on": []},
    "build_packing_list": {"title": "Build packing list", "tool": "packing_list", "reads": [], "depends_on": ["base_packing", "fetch_weather"]},
    "create_calendar_event": {"title": "Create calendar event", "tool": "calendar", "reads": ["destination", "trip_date"], "depends_on": []},
    "load_email_template": {"title": "Load leave email template", "tool": "email_template", "reads": ["recipient"], "depends_on": []},
    "draft_leave_email": {"title": "Draft leave email", "tool": "leave_email", "reads": ["destination", "trip_date"], "depends_on": ["load_email_template"]},
    "fetch_fares": {"title": "Look up fares", "tool": "fares", "reads": ["destination", "trip_date", "travel_mode"], "depends_on": []},
    "compute_budget": {"title": "Compute trip budget", "tool": "budget", "reads": ["max_budget", "currency"], "depends_on": ["fetch_fares"]},
}

# Requirement type -> the task whose evidence its verifier will judge.
REQUIREMENT_TASK = {
    "weather": "fetch_weather",
    "packing_list": "build_packing_list",
    "calendar_event": "create_calendar_event",
    "leave_email": "draft_leave_email",
    "budget": "compute_budget",
}

TASK_ORDER = list(TASKS)


def build_trip_steps(contract):
    """Expand the contract's typed requirements into a dependency-ordered list
    of tasks: understand -> needed tasks -> verify."""
    needed = {}
    for spec in contract.get("requirement_specs", []):
        pending = [REQUIREMENT_TASK[spec["type"]]]
        while pending:
            task_id = pending.pop()
            needed.setdefault(task_id, set()).add(spec["id"])
            pending.extend(TASKS[task_id]["depends_on"])

    steps = [{"id": "understand", "title": "Understand goal", "tool": "mission", "depends_on": [], "reads": [], "requirements": []}]
    for task_id in TASK_ORDER:
        if task_id not in needed:
            continue
        task = TASKS[task_id]
        steps.append({
            "id": task_id,
            "title": task["title"],
            "tool": task["tool"],
            "depends_on": ["understand", *task["depends_on"]],
            "reads": list(task["reads"]),
            "requirements": sorted(needed[task_id]),
        })
    steps.append({"id": "verify", "title": "Verify mission", "tool": "verification", "depends_on": [step["id"] for step in steps[1:]], "reads": [], "requirements": []})
    return steps


# ============================================================
# HELPERS
# ============================================================

def _now():
    return datetime.now(timezone.utc).isoformat()


def _long_date(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%A, %d %B %Y")


def _require(params, *keys):
    missing = [key for key in keys if params.get(key) in (None, "")]
    if missing:
        raise ToolError(f"Missing contract parameter(s): {', '.join(missing)}.")


def _parse_date(iso):
    try:
        return datetime.strptime(str(iso), "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(f"trip_date {iso!r} is not a YYYY-MM-DD date.")


def _upstream(ctx, task_id):
    data = ctx["upstream"].get(task_id)
    if data is None:
        raise ToolError(f"Upstream evidence from {task_id!r} is unavailable.")
    return data


def _write_output(mission_id, filename, text, newline="\n"):
    folder = OUTPUT_DIR / mission_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    content = text.encode("utf-8")
    with open(path, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": len(content)}


def load_fixture(name):
    with open(FIXTURES_DIR / name, encoding="utf-8") as handle:
        return json.load(handle)


# ============================================================
# TOOLS
# ============================================================

def resolve_destination(ctx):
    params = ctx["params"]
    _require(params, "destination")
    info = DESTINATIONS.get(params["destination"])
    if not info:
        raise ToolError(f"{params['destination']!r} is not in the local destination list.")
    data = {"destination": params["destination"], "latitude": info["lat"], "longitude": info["lon"], "source": "local gazetteer"}
    return f"{data['destination']}: lat {data['latitude']}, lon {data['longitude']} (local gazetteer).", data


def http_get_json(url):
    """Network seam; tests replace this to stay offline."""
    request = urllib.request.Request(url, headers={"User-Agent": "HADES/1.0"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _weather_cache_path():
    return CACHE_DIR / "weather.json"


def _read_weather_cache():
    try:
        with open(_weather_cache_path(), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _write_weather_cache(cache):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temp = _weather_cache_path().with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2)
    temp.replace(_weather_cache_path())


def fetch_weather(ctx, today=None):
    params = ctx["params"]
    _require(params, "trip_date")
    place = _upstream(ctx, "resolve_destination")
    trip_date = _parse_date(params["trip_date"])
    today = today or date.today()
    if trip_date < today or trip_date > today + timedelta(days=FORECAST_DAYS - 1):
        raise ToolError(f"{trip_date.isoformat()} is outside the {FORECAST_DAYS}-day forecast window.")

    key = f"{place['latitude']},{place['longitude']},{trip_date.isoformat()}"
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode({
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weather_code",
        "timezone": "Asia/Kolkata",
        "start_date": trip_date.isoformat(),
        "end_date": trip_date.isoformat(),
    })

    cache = _read_weather_cache()
    source = "open-meteo"
    try:
        daily = http_get_json(url)["daily"]
        record = {
            "date": daily["time"][0],
            "temperature_max": daily["temperature_2m_max"][0],
            "temperature_min": daily["temperature_2m_min"][0],
            "precipitation_probability_max": daily["precipitation_probability_max"][0],
            "precipitation_sum": daily["precipitation_sum"][0],
            "weather_code": daily["weather_code"][0],
            "fetched_at": _now(),
        }
        if record["date"] != trip_date.isoformat() or record["precipitation_probability_max"] is None:
            raise ValueError("Forecast response did not cover the requested date.")
        cache[key] = record
        _write_weather_cache(cache)
    except Exception as exc:
        record = cache.get(key)
        if not record:
            raise ToolError(f"Open-Meteo unreachable ({type(exc).__name__}) and no cached forecast for {trip_date.isoformat()}.")
        source = "cache (offline fallback)"

    data = {
        **record,
        "destination": place["destination"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "conditions": WEATHER_CODES.get(record["weather_code"], f"Weather code {record['weather_code']}"),
        "source": source,
    }
    return (
        f"{data['destination']} on {_long_date(data['date'])}: {data['conditions']}, "
        f"{data['temperature_min']}-{data['temperature_max']} °C, "
        f"rain chance {data['precipitation_probability_max']}% ({source}).",
        data,
    )


def base_packing(ctx):
    data = {"items": list(BASE_PACKING)}
    return f"{len(BASE_PACKING)} essentials loaded.", data


def packing_rules(weather):
    """Weather-driven packing rules; the packing verifier reuses them."""
    items = []
    rain = weather.get("precipitation_probability_max") or 0
    if rain > RAIN_THRESHOLD:
        reason = f"Rain chance {rain}% > {RAIN_THRESHOLD}%"
        items += [("Umbrella", reason), ("Raincoat", reason)]
    if (weather.get("temperature_max") or 0) >= 30:
        reason = f"Max temperature {weather['temperature_max']} °C"
        items += [("Sunscreen", reason), ("Cap or hat", reason)]
    if weather.get("temperature_min") is not None and weather["temperature_min"] <= 18:
        items.append(("Light jacket", f"Min temperature {weather['temperature_min']} °C"))
    return items


def build_packing_list(ctx):
    base = _upstream(ctx, "base_packing")
    weather = _upstream(ctx, "fetch_weather")
    items = [{"item": item, "reason": "Essential", "source": "base"} for item in base["items"]]
    items += [{"item": item, "reason": reason, "source": "weather"} for item, reason in packing_rules(weather)]
    data = {
        "items": items,
        "weather_basis": {
            key: weather.get(key)
            for key in ("date", "precipitation_probability_max", "temperature_max", "temperature_min", "conditions")
        },
    }
    weather_items = [entry["item"] for entry in items if entry["source"] == "weather"]
    return (
        f"{len(items)} items for {weather['date']}"
        + (f"; weather adds: {', '.join(weather_items)}." if weather_items else "; no weather-specific items needed."),
        data,
    )


def _ics_escape(value):
    return str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def create_calendar_event(ctx):
    params = ctx["params"]
    _require(params, "destination", "trip_date")
    trip_date = _parse_date(params["trip_date"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = f"Trip to {params['destination']}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HADES//Trip Planner//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{ctx['mission_id']}-trip@hades.local",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{trip_date.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(trip_date + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"LOCATION:{_ics_escape(params['destination'])}",
        f"DESCRIPTION:{_ics_escape('Created by HADES. Not synced to any calendar service.')}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    written = _write_output(ctx["mission_id"], "trip.ics", "\r\n".join(lines), newline="")
    data = {**written, "summary": summary, "trip_date": trip_date.isoformat()}
    return f"Wrote {Path(written['path']).name} for {_long_date(data['trip_date'])}.", data


def load_email_template(ctx):
    params = ctx["params"]
    _require(params, "recipient")
    template = load_fixture("leave_template.json")
    recipient = template["recipients"].get(params["recipient"])
    if not recipient:
        raise ToolError(f"No leave template for recipient {params['recipient']!r}.")
    data = {"recipient": params["recipient"], **recipient, "subject": template["subject"], "body": template["body"]}
    return f"Leave template loaded for {recipient['title']}.", data


def draft_leave_email(ctx):
    params = ctx["params"]
    _require(params, "destination", "trip_date")
    template = _upstream(ctx, "load_email_template")
    values = {
        "salutation": template["salutation"],
        "title": template["title"],
        "destination": params["destination"],
        "date_long": _long_date(_parse_date(params["trip_date"]).isoformat()),
    }
    subject = template["subject"].format(**values)
    body = "\n".join(line.format(**values) for line in template["body"])
    text = (
        "DRAFT - NOT SENT. Review before sending from your own mail client.\n"
        f"To: {template['title']}\n"
        f"Subject: {subject}\n\n"
        f"{body}\n"
    )
    written = _write_output(ctx["mission_id"], "leave_email.txt", text)
    data = {**written, "subject": subject, "recipient": template["recipient"], "trip_date": params["trip_date"]}
    return f"Draft saved to {Path(written['path']).name} (not sent).", data


def fare_options(destination, trip_date):
    fixture = load_fixture("fares.json")
    route = fixture["routes"].get(destination)
    if not route:
        raise ToolError(f"No fare data for {destination!r} in the local fixture.")
    weekday = trip_date.strftime("%A").lower()
    return fixture, route, weekday, route.get(weekday, route["default"])


def fetch_fares(ctx):
    params = ctx["params"]
    _require(params, "destination", "trip_date")
    trip_date = _parse_date(params["trip_date"])
    mode = params.get("travel_mode") or "train"
    fixture, route, weekday, options = fare_options(params["destination"], trip_date)
    selected = next((option for option in options if option["mode"] == mode), None)
    if not selected:
        raise ToolError(f"No {mode} available to {params['destination']} on {weekday.title()}.")
    data = {
        "origin": fixture["origin"],
        "destination": params["destination"],
        "trip_date": trip_date.isoformat(),
        "weekday": weekday,
        "currency": fixture["currency"],
        "travel_mode": mode,
        "options": options,
        "selected": selected,
        "local_expenses": route["local_expenses"],
        "source": "local fixture (fixtures/fares.json)",
    }
    return (
        f"{selected['service']} on {weekday.title()}: ₹{selected['outbound']:,} out, ₹{selected['return']:,} back "
        f"({len(options)} options, local fixture).",
        data,
    )


def compute_budget(ctx):
    params = ctx["params"]
    _require(params, "max_budget")
    fares = _upstream(ctx, "fetch_fares")
    selected = fares["selected"]
    line_items = [
        {"item": f"Outbound: {selected['service']}", "amount": selected["outbound"]},
        {"item": f"Return: {selected['service']}", "amount": selected["return"]},
        *fares["local_expenses"],
    ]
    total = sum(item["amount"] for item in line_items)
    data = {
        "line_items": line_items,
        "total": total,
        "max_budget": params["max_budget"],
        "currency": params.get("currency") or "INR",
        "travel_mode": fares["travel_mode"],
        "trip_date": fares["trip_date"],
    }
    return f"Total ₹{total:,} against a limit of ₹{params['max_budget']:,}.", data


TOOLS = {
    "destination": resolve_destination,
    "weather": fetch_weather,
    "packing_base": base_packing,
    "packing_list": build_packing_list,
    "calendar": create_calendar_event,
    "email_template": load_email_template,
    "leave_email": draft_leave_email,
    "fares": fetch_fares,
    "budget": compute_budget,
}


def run_tool(tool, ctx):
    """Run a trip tool. Returns (output_text, structured_data); raises
    ToolError when no real result could be produced."""
    return TOOLS[tool](ctx)


def trip_summary(contract, evidence_by_task):
    """Markdown deliverable assembled from the latest evidence."""
    params = contract.get("parameters", {})
    lines = [f"# {params.get('destination') or 'Trip'} trip pack", ""]
    weather = evidence_by_task.get("fetch_weather")
    if weather:
        lines += [f"**Weather:** {weather['conditions']}, {weather['temperature_min']}-{weather['temperature_max']} °C, rain chance {weather['precipitation_probability_max']}% ({weather['source']})", ""]
    packing = evidence_by_task.get("build_packing_list")
    if packing:
        lines += ["**Packing list:**"] + [f"- {entry['item']}" + (f" ({entry['reason']})" if entry["source"] == "weather" else "") for entry in packing["items"]] + [""]
    calendar = evidence_by_task.get("create_calendar_event")
    if calendar:
        lines += [f"**Calendar:** `{calendar['path']}`", ""]
    email = evidence_by_task.get("draft_leave_email")
    if email:
        lines += [f"**Leave email draft (not sent):** `{email['path']}`", ""]
    budget = evidence_by_task.get("compute_budget")
    if budget:
        lines += ["**Budget:**"] + [f"- {item['item']}: ₹{item['amount']:,}" for item in budget["line_items"]]
        lines += [f"- **Total: ₹{budget['total']:,}** (limit ₹{budget['max_budget']:,})", ""]
    return "\n".join(lines).strip()


# ============================================================
# DOMAIN REGISTRY
# ============================================================

# The task graph, tools and summaries above are shared by every typed
# domain; other domains (see exam_tools) register into them.
SUMMARIES = {"trip": trip_summary}


def register_domain(domain, tasks, requirement_task, tools, summary):
    clash = (set(tasks) & set(TASKS)) | (set(tools) & set(TOOLS))
    if clash:
        raise ValueError(f"Domain {domain!r} redefines {sorted(clash)}.")
    TASKS.update(tasks)
    TASK_ORDER.extend(tasks)
    REQUIREMENT_TASK.update(requirement_task)
    TOOLS.update(tools)
    SUMMARIES[domain] = summary


def mission_summary(contract, evidence_by_task):
    return SUMMARIES[contract.get("domain") or "trip"](contract, evidence_by_task)
