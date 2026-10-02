"""HADES regression tests. Run from backend/: venv\\Scripts\\python -m unittest discover -s tests -v"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

# Keep tests provider-free: load_dotenv() does not override variables that
# are already set, so these win over backend/.env.
os.environ["HADES_AI_ENHANCEMENTS"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import goal_compiler  # noqa: E402
import main  # noqa: E402
import exam_tools  # noqa: E402
import trip_tools  # noqa: E402
import verifiers  # noqa: E402

TEMP_DIR = Path(tempfile.mkdtemp(prefix="hades-tests-"))
trip_tools.OUTPUT_DIR = TEMP_DIR / "outputs"
trip_tools.CACHE_DIR = TEMP_DIR / "cache"


def fake_open_meteo(rain=70, tmax=27.0, tmin=19.0):
    """Offline stand-in for Open-Meteo that answers for the requested date."""
    def respond(url):
        day = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["start_date"][0]
        return {"daily": {
            "time": [day],
            "temperature_2m_max": [tmax],
            "temperature_2m_min": [tmin],
            "precipitation_probability_max": [rain],
            "precipitation_sum": [4.2],
            "weather_code": [63],
        }}
    return respond


def offline(url):
    raise OSError("network disabled in tests")


# No test reaches the real network unless it patches this seam.
trip_tools.http_get_json = offline


def tearDownModule():
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

BENGALURU_GOAL = (
    "Get me ready for my Bengaluru trip on Friday: check the weather, build a packing "
    "list, add it to my calendar, draft a leave email to my manager, keep total cost "
    "under ₹4,000"
)
FRIDAY = date(2026, 10, 2)


class DecompositionTests(unittest.TestCase):

    def test_bengaluru_goal_has_five_typed_requirements(self):
        result = goal_compiler.decompose_goal(BENGALURU_GOAL, today=FRIDAY)
        specs = result["requirements"]
        self.assertEqual(
            [spec["type"] for spec in specs],
            ["weather", "packing_list", "calendar_event", "leave_email", "budget"],
        )
        self.assertEqual(
            [spec["verifier"] for spec in specs],
            ["verify_weather", "verify_packing_list", "verify_calendar_event", "verify_leave_email", "verify_budget"],
        )
        for spec in specs:
            self.assertEqual(spec["unresolved"], [], spec["id"])
            self.assertTrue(spec["id"].startswith("req_"))
        by_type = {spec["type"]: spec for spec in specs}
        self.assertEqual(by_type["weather"]["parameters"], {"destination": "Bengaluru", "trip_date": "2026-10-09"})
        self.assertEqual(by_type["budget"]["parameters"]["max_budget"], 4000)
        self.assertEqual(by_type["leave_email"]["parameters"]["recipient"], "manager")
        self.assertEqual(by_type["packing_list"]["depends_on"], ["req_weather"])

    def test_date_extraction(self):
        cases = {
            "trip on Sunday": "2026-10-04",
            "trip on Friday": "2026-10-09",
            "leave tomorrow": "2026-10-03",
            "on 2026-11-20": "2026-11-20",
            "on 15 Oct": "2026-10-15",
            "on Jan 3rd": "2027-01-03",
        }
        for text, expected in cases.items():
            found, _ = goal_compiler.extract_date(text, FRIDAY)
            self.assertEqual(found.isoformat(), expected, text)

    def test_budget_extraction(self):
        self.assertEqual(goal_compiler.extract_budget("keep it under ₹4,000"), 4000)
        self.assertEqual(goal_compiler.extract_budget("budget of Rs. 5k"), 5000)
        self.assertIsNone(goal_compiler.extract_budget("Create a 3 item checklist"))

    def test_unrelated_goals_keep_legacy_contract(self):
        for goal in (
            "Create a 3 item checklist for a reliable HADES hackathon demo",
            "Transfer ₹5,000 from my savings account to my landlord",
            "Research the latest advances in electric vehicle battery pack technology",
        ):
            self.assertIsNone(goal_compiler.decompose_goal(goal, today=FRIDAY), goal)
            contract, _ = main.compile_goal(goal)
            self.assertEqual(contract["compiler"]["method"], "legacy")
            self.assertNotIn("requirement_specs", contract)

    def test_budget_alone_is_not_a_typed_goal(self):
        self.assertIsNone(goal_compiler.decompose_goal("Buy a laptop under ₹40,000", today=FRIDAY))


class LlmValidationTests(unittest.TestCase):

    def setUp(self):
        self.rules = goal_compiler.decompose_goal(BENGALURU_GOAL, today=FRIDAY)
        self.proposal = {
            "requirements": [
                {
                    "id": spec["id"],
                    "type": spec["type"],
                    "verifier": spec["verifier"],
                    "parameters": dict(spec["parameters"]),
                    "depends_on": list(spec["depends_on"]),
                }
                for spec in self.rules["requirements"]
            ]
        }

    def validate(self):
        return goal_compiler.validate_decomposition(self.proposal, BENGALURU_GOAL, self.rules, today=FRIDAY)

    def test_valid_proposal_is_accepted(self):
        result = self.validate()
        self.assertEqual(len(result["requirements"]), 5)

    def test_unknown_type_rejected(self):
        self.proposal["requirements"][0]["type"] = "book_hotel"
        with self.assertRaisesRegex(ValueError, "Unknown requirement type"):
            self.validate()

    def test_wrong_verifier_rejected(self):
        self.proposal["requirements"][0]["verifier"] = "always_pass"
        with self.assertRaisesRegex(ValueError, "Verifier"):
            self.validate()

    def test_invented_date_rejected(self):
        self.proposal["requirements"][0]["parameters"]["trip_date"] = "2026-10-10"
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.validate()

    def test_changed_budget_rejected(self):
        self.proposal["requirements"][4]["parameters"]["max_budget"] = 9000
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.validate()

    def test_cycle_rejected(self):
        self.proposal["requirements"][0]["depends_on"] = ["req_packing_list"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.validate()

    def test_dropped_requirement_rejected(self):
        self.proposal["requirements"].pop()
        with self.assertRaisesRegex(ValueError, "omits"):
            self.validate()

    def test_garbage_rejected(self):
        with self.assertRaises(ValueError):
            goal_compiler.validate_decomposition(None, BENGALURU_GOAL, self.rules, today=FRIDAY)


class ScenarioTests(unittest.TestCase):
    """End-to-end flows that must keep working."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def plan(self, goal):
        data = self.client.post("/plan", json={"goal": goal}).json()
        self.assertEqual(data["status"], "success")
        return data["plan"]

    def execute(self, plan):
        response = self.client.post(
            "/execute-approved-stream",
            json={"goal": plan["goal"], "plan": plan, "approved": True},
        )
        self.assertEqual(response.status_code, 200)
        return main.MISSIONS[plan["id"]]

    def recover(self, mission_id):
        approval = self.client.post("/workspace/approve-recovery", json={"mission_id": mission_id, "approved": True}).json()
        self.assertEqual(approval["status"], "success")
        response = self.client.post(f"/mission/reexecute/{mission_id}")
        self.assertEqual(response.status_code, 200)
        return main.MISSIONS[mission_id]

    def test_checklist_completes(self):
        mission = self.execute(self.plan("Create a 3 item checklist for a reliable HADES hackathon demo"))
        self.assertEqual(mission["status"], "complete")
        self.assertTrue(mission["verification"]["passed"])

    def test_guided_demo_recovers_then_completes(self):
        plan = self.client.post("/demo/plan").json()["plan"]
        mission = self.execute(plan)
        self.assertEqual(mission["status"], "recovery_required")
        mission = self.recover(plan["id"])
        self.assertEqual(mission["status"], "complete")
        self.assertEqual(mission["recovery_attempts"], 1)

    def test_funds_transfer_blocks_after_one_recovery(self):
        plan = self.plan("Transfer ₹5,000 from my savings account to my landlord")
        self.assertEqual(plan["approval"]["risk"], "HIGH")
        mission = self.execute(plan)
        self.assertEqual(mission["status"], "recovery_required")
        mission = self.recover(plan["id"])
        self.assertEqual(mission["status"], "blocked")
        self.assertEqual(mission["recovery_attempts"], 1)

    def test_bengaluru_plan_exposes_typed_requirements(self):
        plan = self.plan(BENGALURU_GOAL)
        contract = plan["contract"]
        self.assertEqual(contract["compiler"]["method"], "rules")
        self.assertEqual(len(contract["requirement_specs"]), 5)
        self.assertEqual(len(contract["requirements"]), 5)
        self.assertEqual(contract["parameters"]["destination"], "Bengaluru")
        self.assertEqual(contract["parameters"]["max_budget"], 4000)


class TripToolTests(unittest.TestCase):

    def setUp(self):
        shutil.rmtree(trip_tools.CACHE_DIR, ignore_errors=True)
        self.trip_date = (date.today() + timedelta(days=3)).isoformat()
        self.place = trip_tools.resolve_destination({"params": {"destination": "Bengaluru"}, "upstream": {}})[1]

    def weather(self, fetch, trip_date=None):
        trip_tools.http_get_json = fetch
        try:
            return trip_tools.fetch_weather({
                "params": {"trip_date": trip_date or self.trip_date},
                "upstream": {"resolve_destination": self.place},
            })[1]
        finally:
            trip_tools.http_get_json = offline

    def test_steps_record_inputs_and_dependencies(self):
        contract, _ = main.compile_goal(BENGALURU_GOAL)
        steps = {step["id"]: step for step in main.build_steps(contract)}
        self.assertEqual(len(steps), 11)
        self.assertEqual(steps["fetch_weather"]["reads"], ["trip_date"])
        self.assertIn("resolve_destination", steps["fetch_weather"]["depends_on"])
        self.assertIn("fetch_weather", steps["build_packing_list"]["depends_on"])
        self.assertIn("fetch_fares", steps["compute_budget"]["depends_on"])
        date_free = [step_id for step_id, step in steps.items() if "trip_date" not in step["reads"] and step["depends_on"] == ["understand"]]
        self.assertEqual(sorted(date_free), ["base_packing", "load_email_template", "resolve_destination"])

    def test_weather_live_then_cache_fallback(self):
        live = self.weather(fake_open_meteo(rain=70))
        self.assertEqual(live["source"], "open-meteo")
        self.assertEqual(live["precipitation_probability_max"], 70)
        cached = self.weather(offline)
        self.assertEqual(cached["source"], "cache (offline fallback)")
        self.assertEqual(cached["precipitation_probability_max"], 70)

    def test_weather_offline_without_cache_fails(self):
        with self.assertRaisesRegex(trip_tools.ToolError, "no cached forecast"):
            self.weather(offline)

    def test_weather_outside_forecast_window_fails(self):
        with self.assertRaisesRegex(trip_tools.ToolError, "forecast window"):
            self.weather(fake_open_meteo(), trip_date=(date.today() + timedelta(days=40)).isoformat())

    def test_packing_follows_rain_rule(self):
        base = trip_tools.base_packing({})[1]
        for rain, expected in ((70, True), (50, False)):
            weather = {"date": self.trip_date, "precipitation_probability_max": rain, "temperature_max": 27, "temperature_min": 19, "conditions": "Rain"}
            items = [entry["item"] for entry in trip_tools.build_packing_list({"upstream": {"base_packing": base, "fetch_weather": weather}})[1]["items"]]
            self.assertEqual("Umbrella" in items and "Raincoat" in items, expected, rain)

    def test_calendar_writes_ics(self):
        data = trip_tools.create_calendar_event({"mission_id": "test-cal", "params": {"destination": "Bengaluru", "trip_date": "2026-10-09"}})[1]
        text = Path(data["path"]).read_text(encoding="utf-8")
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("DTSTART;VALUE=DATE:20261009", text)
        self.assertIn(b"\r\nEND:VCALENDAR\r\n", Path(data["path"]).read_bytes())

    def test_leave_email_is_a_draft_with_date(self):
        template = trip_tools.load_email_template({"params": {"recipient": "manager"}})[1]
        data = trip_tools.draft_leave_email({"mission_id": "test-mail", "params": {"destination": "Bengaluru", "trip_date": "2026-10-09"}, "upstream": {"load_email_template": template}})[1]
        text = Path(data["path"]).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("DRAFT - NOT SENT"))
        self.assertIn("Friday, 09 October 2026", text)

    def budget_total(self, trip_date, mode="train"):
        fares = trip_tools.fetch_fares({"params": {"destination": "Bengaluru", "trip_date": trip_date, "travel_mode": mode}})[1]
        return trip_tools.compute_budget({"params": {"max_budget": 4000, "currency": "INR"}, "upstream": {"fetch_fares": fares}})[1]["total"]

    def test_fare_fixture_totals(self):
        self.assertEqual(self.budget_total("2026-10-09"), 3600)          # Friday train
        self.assertEqual(self.budget_total("2026-10-04"), 4600)          # Sunday train
        self.assertEqual(self.budget_total("2026-10-04", "bus"), 3200)   # Sunday night bus


def run_bengaluru_mission(rain=70):
    client = TestClient(main.app)
    plan = client.post("/plan", json={"goal": BENGALURU_GOAL}).json()["plan"]
    trip_tools.http_get_json = fake_open_meteo(rain=rain)
    try:
        client.post("/execute-approved-stream", json={"goal": plan["goal"], "plan": plan, "approved": True})
    finally:
        trip_tools.http_get_json = offline
    return main.MISSIONS[plan["id"]]


class TripMissionTests(unittest.TestCase):

    def test_bengaluru_mission_runs_real_tools(self):
        mission = run_bengaluru_mission()
        plan = mission
        latest = main.latest_evidence(mission)
        tool_steps = [step["id"] for step in mission["steps"] if step["tool"] not in {"mission", "verification"}]
        self.assertEqual(len(tool_steps), 9)
        for task_id in tool_steps:
            self.assertEqual(latest[task_id]["status"], "complete", f"{task_id}: {latest[task_id]['output']}")
            self.assertIsNotNone(latest[task_id]["data"])
        self.assertEqual(latest["build_packing_list"]["upstream_evidence"]["fetch_weather"], latest["fetch_weather"]["id"])
        self.assertEqual(latest["fetch_weather"]["inputs"]["parameters"], {"trip_date": plan["contract"]["parameters"]["trip_date"]})
        self.assertTrue(Path(latest["create_calendar_event"]["data"]["path"]).exists())
        self.assertTrue(Path(latest["draft_leave_email"]["data"]["path"]).exists())
        self.assertIn("trip pack", mission["artifacts"][-1])
        results = mission["verification"]["requirement_results"]
        self.assertEqual([item["verifier"] for item in results], [
            "verify_weather", "verify_packing_list", "verify_calendar_event", "verify_leave_email", "verify_budget",
        ])
        self.assertTrue(all(item["status"] == "satisfied" for item in results), [item["reason"] for item in results])
        self.assertTrue(all(item["evidence_id"] for item in results))
        self.assertEqual(mission["status"], "complete")
        self.assertIn("₹3,600", results[4]["reason"])


class VerifierTests(unittest.TestCase):
    """Verifiers judge the real artifact, so tampering with it must fail them
    even though the producing tool reported success."""

    @classmethod
    def setUpClass(cls):
        cls.mission = run_bengaluru_mission(rain=70)
        cls.trip_date = cls.mission["contract"]["parameters"]["trip_date"]

    def check(self, requirement_type, mutate=None):
        mission = main.MISSIONS[self.mission["id"]]
        evidence = json.loads(json.dumps(mission["evidence"]))
        latest = {}
        for item in evidence:
            latest[item["step"]] = item
        if mutate:
            mutate(latest)
        result, _ = main.verify_typed(mission["contract"], evidence)
        return next(item for item in result["requirement_results"] if item["requirement_id"] == f"req_{requirement_type}")

    def assert_fails(self, requirement_type, mutate, fragment):
        result = self.check(requirement_type, mutate)
        self.assertEqual(result["status"], "missing")
        self.assertIn(fragment, result["reason"])

    def test_all_pass_unmodified(self):
        for kind in ("weather", "packing_list", "calendar_event", "leave_email", "budget"):
            self.assertEqual(self.check(kind)["status"], "satisfied", kind)

    def test_weather_must_match_cached_forecast(self):
        self.assert_fails("weather", lambda latest: latest["fetch_weather"]["data"].update(precipitation_probability_max=5), "differs from the cached")

    def test_weather_must_be_for_trip_date(self):
        self.assert_fails("weather", lambda latest: latest["fetch_weather"]["data"].update(date="2026-01-01"), "but the trip is on")

    def test_packing_needs_rain_gear(self):
        def drop_umbrella(latest):
            data = latest["build_packing_list"]["data"]
            data["items"] = [entry for entry in data["items"] if entry["item"] != "Umbrella"]
        self.assert_fails("packing_list", drop_umbrella, "requires Umbrella")

    def test_packing_must_use_latest_weather(self):
        self.assert_fails("packing_list", lambda latest: latest["build_packing_list"]["upstream_evidence"].update(fetch_weather="ev0"), "older weather evidence")

    def test_calendar_file_is_parsed(self):
        path = Path(main.latest_evidence(self.mission)["create_calendar_event"]["data"]["path"])
        original = path.read_bytes()
        try:
            path.write_bytes(original.replace(self.trip_date.replace("-", "").encode(), b"20300101"))
            self.assert_fails("calendar_event", None, "starts on 2030-01-01")
            path.write_bytes(b"not a calendar")
            self.assert_fails("calendar_event", None, "not a valid calendar file")
            path.unlink()
            self.assert_fails("calendar_event", None, "does not exist")
        finally:
            path.write_bytes(original)

    def test_email_must_contain_trip_date(self):
        path = Path(main.latest_evidence(self.mission)["draft_leave_email"]["data"]["path"])
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace(verifiers._long_date(self.trip_date), "Saturday, 01 January 2030"), encoding="utf-8")
            self.assert_fails("leave_email", None, "does not mention the trip date")
        finally:
            path.write_text(original, encoding="utf-8")

    def test_budget_resums_line_items(self):
        self.assert_fails("budget", lambda latest: latest["compute_budget"]["data"]["line_items"][0].update(amount=10), "but the tool reported")

    def test_budget_ignores_tool_total(self):
        def understate(latest):
            data = latest["compute_budget"]["data"]
            data["line_items"][0]["amount"] = 10
            data["total"] = sum(item["amount"] for item in data["line_items"])
        self.assert_fails("budget", understate, "does not match the")

    def test_budget_over_limit_on_sunday(self):
        spec = next(item for item in self.mission["contract"]["requirement_specs"] if item["type"] == "budget")
        sunday = dict(spec, parameters=dict(spec["parameters"], trip_date="2026-10-04"))
        record = {"id": "evX", "status": "complete", "data": {
            "line_items": [{"item": "train", "amount": 3600}, {"item": "local", "amount": 1000}], "total": 4600,
        }}
        contract = {"parameters": {"destination": "Bengaluru", "travel_mode": "train"}}
        passed, reason = verifiers.verify_budget(sunday, record, {}, contract)
        self.assertFalse(passed)
        self.assertIn("₹4,600", reason)
        self.assertIn("exceeds the ₹4,000 limit by ₹600", reason)
        record["data"] = {"line_items": [{"item": "bus", "amount": 2200}, {"item": "local", "amount": 1000}], "total": 3200}
        passed, reason = verifiers.verify_budget(sunday, record, {}, {"parameters": {"destination": "Bengaluru", "travel_mode": "bus"}})
        self.assertTrue(passed, reason)

    def test_stale_evidence_fails(self):
        self.assert_fails("weather", lambda latest: latest["fetch_weather"].update(status="stale", stale_reason="trip_date changed"), "is stale")


def sse_events(text):
    events = []
    for block in text.split("\n\n"):
        lines = block.splitlines()
        name = next((line[6:].strip() for line in lines if line.startswith("event:")), None)
        data = "\n".join(line[5:].strip() for line in lines if line.startswith("data:"))
        if name and data:
            events.append((name, json.loads(data)))
    return events


class ChangeParsingTests(unittest.TestCase):

    def test_chat_text_to_changes(self):
        self.assertEqual(goal_compiler.parse_change_text("trip moved to Sunday", FRIDAY), {"trip_date": "2026-10-04"})
        self.assertEqual(goal_compiler.parse_change_text("switch to the night bus", FRIDAY), {"travel_mode": "bus"})
        self.assertEqual(goal_compiler.parse_change_text("raise budget to ₹4,600", FRIDAY), {"max_budget": 4600})
        self.assertEqual(goal_compiler.parse_change_text("nothing relevant", FRIDAY), {})

    def test_weekday_is_never_a_destination(self):
        self.assertIsNone(goal_compiler.extract_destination("move the trip to Sunday"))

    def test_normalize_changes(self):
        self.assertEqual(goal_compiler.normalize_changes({"trip_date": "Sunday"}, FRIDAY), {"trip_date": "2026-10-04"})
        self.assertEqual(goal_compiler.normalize_changes({"max_budget": "₹4,600"}, FRIDAY), {"max_budget": 4600})
        for bad in ({"hotel": "x"}, {"travel_mode": "plane"}, {"trip_date": "someday"}, {"destination": "Atlantis"}, {}):
            with self.assertRaises(ValueError, msg=bad):
                goal_compiler.normalize_changes(bad, FRIDAY)

    def test_stale_closure_follows_reads_and_dependencies(self):
        contract, _ = main.compile_goal(BENGALURU_GOAL)
        steps = main.build_steps(contract)
        self.assertEqual(main.stale_closure(steps, {"trip_date"}), [
            "fetch_weather", "build_packing_list", "create_calendar_event",
            "draft_leave_email", "fetch_fares", "compute_budget",
        ])
        self.assertEqual(main.stale_closure(steps, {"max_budget"}), ["compute_budget"])
        self.assertEqual(main.stale_closure(steps, {"travel_mode"}), ["fetch_fares", "compute_budget"])


class ChangeEndpointTests(unittest.TestCase):

    def change(self, mission_id, rain=70, **body):
        trip_tools.http_get_json = fake_open_meteo(rain=rain)
        try:
            return TestClient(main.app).post(f"/mission/{mission_id}/change", json=body)
        finally:
            trip_tools.http_get_json = offline

    def test_trip_moved_to_sunday(self):
        mission = run_bengaluru_mission()
        self.assertEqual(mission["status"], "complete")
        before = {item["step"]: item["id"] for item in mission["evidence"]}

        response = self.change(mission["id"], text="trip moved to Sunday")
        self.assertEqual(response.status_code, 200)
        change = dict(sse_events(response.text))["change"]["change"]
        self.assertEqual(change["message"], "Re-executing 6 of 10 tasks")
        self.assertEqual(change["diff"]["trip_date"]["after"], goal_compiler.resolve_weekday("sunday", date.today()).isoformat())
        self.assertEqual(len(change["stale_evidence"]), 6)
        self.assertEqual(sorted(change["unaffected_steps"]), ["base_packing", "load_email_template", "resolve_destination", "understand"])

        mission = main.MISSIONS[mission["id"]]
        runs = {}
        for item in mission["evidence"]:
            runs.setdefault(item["step"], []).append(item)
        for step_id in change["unaffected_steps"]:
            self.assertEqual([item["id"] for item in runs[step_id]], [before[step_id]], f"{step_id} must not re-run")
            self.assertEqual(runs[step_id][0]["status"], "complete")
        for step_id in change["rerun_steps"]:
            self.assertEqual([item["status"] for item in runs[step_id]], ["stale", "complete"], step_id)
            self.assertEqual(runs[step_id][-1]["trigger"], "change")

        results = {item["requirement_id"]: item for item in mission["verification"]["requirement_results"]}
        for requirement_id in ("req_weather", "req_packing_list", "req_calendar_event", "req_leave_email"):
            self.assertEqual(results[requirement_id]["status"], "satisfied", results[requirement_id]["reason"])
        self.assertEqual(results["req_budget"]["status"], "missing")
        self.assertIn("exceeds the ₹4,000 limit by ₹600", results["req_budget"]["reason"])
        # A user-requested change does not consume the single recovery attempt.
        self.assertEqual(mission["recovery_attempts"], 0)
        self.assertEqual(mission["status"], "recovery_required")
        self.assertEqual(mission["recovery"]["kind"], "amendment")

        # Raising only the budget re-runs only the budget task.
        response = self.change(mission["id"], changes={"max_budget": 4600})
        change = dict(sse_events(response.text))["change"]["change"]
        self.assertEqual(change["message"], "Re-executing 1 of 10 tasks")
        self.assertEqual(change["rerun_steps"], ["compute_budget"])
        self.assertEqual(main.MISSIONS[mission["id"]]["status"], "complete")

    def test_change_rejections(self):
        client = TestClient(main.app)
        planned = client.post("/plan", json={"goal": BENGALURU_GOAL}).json()["plan"]
        self.assertEqual(self.change(planned["id"], text="trip moved to Sunday").status_code, 409)
        legacy = client.post("/plan", json={"goal": "Create a 3 item checklist for a demo"}).json()["plan"]
        self.assertEqual(self.change(legacy["id"], text="moved to Sunday").status_code, 400)
        mission = run_bengaluru_mission()
        self.assertEqual(self.change(mission["id"], text="hello there").status_code, 400)
        same_day = mission["contract"]["parameters"]["trip_date"]
        self.assertEqual(self.change(mission["id"], changes={"trip_date": same_day}).status_code, 400)
        self.assertEqual(self.change("nope", text="moved to Sunday").status_code, 404)


class AmendmentTests(unittest.TestCase):

    def sunday_mission(self):
        mission = run_bengaluru_mission()
        trip_tools.http_get_json = fake_open_meteo(rain=70)
        try:
            TestClient(main.app).post(f"/mission/{mission['id']}/change", json={"text": "trip moved to Sunday"})
        finally:
            trip_tools.http_get_json = offline
        mission = main.MISSIONS[mission["id"]]
        self.assertEqual(mission["status"], "recovery_required")
        return mission

    def amend(self, mission_id, **body):
        return TestClient(main.app).post(f"/mission/{mission_id}/amend", json=body)

    def test_options_are_structured_diffs(self):
        recovery = self.sunday_mission()["recovery"]
        self.assertEqual(recovery["kind"], "amendment")
        self.assertEqual(recovery["status"], "approval_required")
        options = {option["id"]: option for option in recovery["options"]}
        self.assertEqual(set(options), {"raise_budget", "switch_to_bus"})
        self.assertEqual(options["raise_budget"]["diff"], {"max_budget": {"before": 4000, "after": 4600}})
        self.assertEqual(options["switch_to_bus"]["diff"], {"travel_mode": {"before": "train", "after": "bus"}})
        self.assertIn("₹3,200", options["switch_to_bus"]["label"])
        self.assertEqual(options["raise_budget"]["rerun_preview"], ["compute_budget"])
        self.assertEqual(options["switch_to_bus"]["rerun_preview"], ["fetch_fares", "compute_budget"])

    def test_switch_to_bus_completes(self):
        mission = self.sunday_mission()
        response = self.amend(mission["id"], option_id="switch_to_bus")
        events = dict(sse_events(response.text))
        self.assertEqual(events["amendment"]["change"]["message"], "Re-executing 2 of 10 tasks")
        mission = main.MISSIONS[mission["id"]]
        self.assertEqual(mission["status"], "complete")
        self.assertEqual(mission["contract"]["parameters"]["travel_mode"], "bus")
        self.assertEqual([item["option_id"] for item in mission["contract"]["amendments"]], ["switch_to_bus"])
        budget = next(item for item in mission["verification"]["requirement_results"] if item["requirement_id"] == "req_budget")
        self.assertIn("Total ₹3,200", budget["reason"])
        self.assertEqual(mission["recovery"]["status"], "resolved")
        self.assertEqual(mission["recovery_attempts"], 0)

    def test_raise_budget_completes(self):
        mission = self.sunday_mission()
        events = dict(sse_events(self.amend(mission["id"], option_id="raise_budget").text))
        self.assertEqual(events["amendment"]["change"]["rerun_steps"], ["compute_budget"])
        mission = main.MISSIONS[mission["id"]]
        self.assertEqual(mission["status"], "complete")
        self.assertEqual(mission["contract"]["parameters"]["max_budget"], 4600)
        self.assertIn("Total trip cost must not exceed ₹4,600", mission["contract"]["constraints"])

    def test_reject_all_blocks(self):
        mission = self.sunday_mission()
        data = self.amend(mission["id"], reject=True).json()
        self.assertEqual(data["mission"]["status"], "blocked")
        self.assertEqual(data["mission"]["recovery"]["status"], "rejected")
        self.assertEqual(self.amend(mission["id"], option_id="raise_budget").status_code, 409)

    def test_unknown_option_and_plain_approval_refused(self):
        mission = self.sunday_mission()
        self.assertEqual(self.amend(mission["id"], option_id="free_trip").status_code, 400)
        data = TestClient(main.app).post("/workspace/approve-recovery", json={"mission_id": mission["id"], "approved": True}).json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(main.MISSIONS[mission["id"]]["recovery"]["status"], "approval_required")


class AutoRetryTests(unittest.TestCase):
    """Retries inside the contract run without approval and still respect the
    single-attempt limit."""

    def run_with(self, fetch):
        shutil.rmtree(trip_tools.CACHE_DIR, ignore_errors=True)
        client = TestClient(main.app)
        plan = client.post("/plan", json={"goal": BENGALURU_GOAL}).json()["plan"]
        trip_tools.http_get_json = fetch
        try:
            response = client.post("/execute-approved-stream", json={"goal": plan["goal"], "plan": plan, "approved": True})
        finally:
            trip_tools.http_get_json = offline
        return main.MISSIONS[plan["id"]], [name for name, _ in sse_events(response.text)]

    def test_transient_failure_recovers_without_approval(self):
        calls = {"count": 0}
        live = fake_open_meteo(rain=70)

        def flaky(url):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("temporary outage")
            return live(url)

        mission, names = self.run_with(flaky)
        self.assertEqual(mission["status"], "complete")
        self.assertEqual(mission["recovery_attempts"], 1)
        self.assertIn("recovery", names)
        self.assertNotIn("recovery_required", names)
        self.assertEqual(names.count("complete"), 1)
        retried = [item["step"] for item in mission["evidence"] if item.get("trigger") == "recovery"]
        self.assertEqual(retried, ["fetch_weather", "build_packing_list", "verify"])

    def test_persistent_failure_blocks_after_one_retry(self):
        mission, names = self.run_with(offline)
        self.assertEqual(mission["status"], "blocked")
        self.assertEqual(mission["recovery_attempts"], 1)
        self.assertIn("blocked", names)
        self.assertNotIn("recovery_required", names)


class AuditChainTests(unittest.TestCase):

    def test_events_are_hash_chained(self):
        mission = run_bengaluru_mission()
        events = mission["events"]
        self.assertEqual(events[0]["prev_hash"], main.GENESIS_HASH)
        for previous, current in zip(events, events[1:]):
            self.assertEqual(current["prev_hash"], previous["hash"])
            self.assertEqual(len(current["hash"]), 64)
        self.assertEqual(main.verify_event_chain(events), (True, None))

    def test_tampering_is_detected(self):
        events = json.loads(json.dumps(run_bengaluru_mission()["events"]))
        events[3]["message"] = "rewritten history"
        self.assertEqual(main.verify_event_chain(events), (False, 4))
        events = json.loads(json.dumps(run_bengaluru_mission()["events"]))
        del events[2]
        self.assertFalse(main.verify_event_chain(events)[0])

    def test_metadata_is_snapshotted(self):
        mission = {"id": "m", "events": []}
        live = {"status": "approval_required"}
        main.log(mission, "recovery_required", "x", live)
        live["status"] = "resolved"
        self.assertEqual(mission["events"][0]["metadata"]["status"], "approval_required")
        self.assertTrue(main.verify_event_chain(mission["events"])[0])


class ReceiptTests(unittest.TestCase):

    def test_receipt_after_change_and_amendment(self):
        mission = AmendmentTests.sunday_mission(self)
        TestClient(main.app).post(f"/mission/{mission['id']}/amend", json={"option_id": "switch_to_bus"})
        response = TestClient(main.app).get(f"/mission/{mission['id']}/receipt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["content-disposition"])
        receipt = response.json()

        self.assertEqual(receipt["mission"]["status"], "complete")
        self.assertEqual(receipt["contract"]["parameters"]["travel_mode"], "bus")
        self.assertEqual(receipt["contract"]["amendments"][0]["option_id"], "switch_to_bus")
        self.assertEqual(len(receipt["requirements"]), 5)
        for requirement in receipt["requirements"]:
            self.assertEqual(requirement["status"], "satisfied", requirement["reason"])
            self.assertTrue(requirement["verifier"].startswith("verify_"))
            self.assertTrue(requirement["reason"])
            self.assertEqual(requirement["evidence"]["status"], "complete")
        files = [item["evidence"]["file"] for item in receipt["requirements"] if item["evidence"]["file"]]
        self.assertEqual(len(files), 2)
        self.assertTrue(all(item["intact"] for item in files))
        packing = next(item for item in receipt["requirements"] if item["type"] == "packing_list")
        self.assertIn("fetch_weather", [item["step"] for item in packing["upstream_evidence"]])

        chain = receipt["chain"]
        self.assertTrue(chain["valid"])
        self.assertEqual(chain["final_hash"], receipt["event_log"][-1]["hash"])
        self.assertEqual(main.verify_event_chain(receipt["event_log"]), (True, None))
        self.assertEqual(receipt["llm_calls"], {"planning": 0, "execution": 0, "recovery": 0, "verification": 0, "total": 0})

        body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        self.assertEqual(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), receipt["receipt_sha256"])
        self.assertEqual(main.MISSIONS[mission["id"]]["events"][-1]["kind"], "receipt_exported")

    def test_legacy_receipt(self):
        client = TestClient(main.app)
        plan = client.post("/plan", json={"goal": "Create a 3 item checklist for a reliable HADES hackathon demo"}).json()["plan"]
        client.post("/execute-approved-stream", json={"goal": plan["goal"], "plan": plan, "approved": True})
        receipt = client.get(f"/mission/{plan['id']}/receipt").json()
        self.assertTrue(receipt["chain"]["valid"])
        self.assertEqual(receipt["requirements"][0]["status"], "satisfied")


class LlmCounterTests(unittest.TestCase):

    def test_verification_phase_is_refused(self):
        with self.assertRaises(RuntimeError):
            main.llm_call("judge this", "verification")

    def test_provider_requests_are_counted_by_phase(self):
        original_gemini, original_enabled = main.gemini, main.ai_enhancements_enabled

        def fake_gemini(prompt, grounded=False, on_request=None):
            on_request("GEMINI")
            return '{"requirements": [{"type": "teleport"}]}', "GEMINI"

        main.gemini, main.ai_enhancements_enabled = fake_gemini, lambda: True
        before = dict(main.LLM_CALLS)
        try:
            plan = TestClient(main.app).post("/plan", json={"goal": BENGALURU_GOAL}).json()["plan"]
        finally:
            main.gemini, main.ai_enhancements_enabled = original_gemini, original_enabled
        self.assertEqual(plan["llm_calls"], {"planning": 1, "execution": 0, "recovery": 0, "verification": 0})
        self.assertEqual(main.LLM_CALLS["planning"], before["planning"] + 1)
        self.assertEqual(main.LLM_CALLS["verification"], 0)
        # The invalid proposal was rejected; rules were used instead.
        self.assertIn("Unknown requirement type", plan["contract"]["compiler"]["llm_rejected"])
        self.assertEqual(len(plan["contract"]["requirement_specs"]), 5)

    def test_endpoint(self):
        totals = TestClient(main.app).get("/llm-calls").json()["totals"]
        self.assertEqual(totals["verification"], 0)
        self.assertEqual(set(totals), {"planning", "execution", "recovery", "verification", "total"})


EXAM_GOAL = "prepare me for my physics exam on Monday"


class ClassificationTests(unittest.TestCase):

    def test_rule_based_kinds(self):
        cases = {
            "hi": "CHAT",
            "hello there!": "CHAT",
            "thanks": "CHAT",
            "what is the capital of France?": "QUESTION",
            "how do I make pasta?": "QUESTION",
            "Is it going to rain tomorrow": "QUESTION",
            EXAM_GOAL: "GOAL",
            BENGALURU_GOAL: "GOAL",
            "Create a 3 item checklist for a reliable HADES hackathon demo": "GOAL",
            "Transfer ₹5,000 from my savings account to my landlord": "GOAL",
            "Research the latest advances in electric vehicle battery technology and summarize the key findings.": "GOAL",
            "Can you prepare a study plan for my chemistry exam on Friday?": "GOAL",
            "Could you write a summary of this project": "GOAL",
        }
        for text, expected in cases.items():
            self.assertEqual(goal_compiler.classify_input(text)[0], expected, text)

    def plan(self, text):
        before = len(main.MISSIONS)
        data = TestClient(main.app).post("/plan", json={"goal": text}).json()
        return data, len(main.MISSIONS) - before

    def test_hi_creates_no_mission(self):
        data, created = self.plan("hi")
        self.assertEqual(created, 0)
        self.assertEqual(data["status"], "not_a_goal")
        self.assertEqual(data["kind"], "CHAT")
        self.assertIn("not a goal. HADES executes goals.", data["message"])
        self.assertEqual(len(data["examples"]), 2)
        self.assertIsNone(data["quick_answer"])

    def test_question_creates_no_mission(self):
        data, created = self.plan("what is the capital of France?")
        self.assertEqual(created, 0)
        self.assertEqual(data["kind"], "QUESTION")
        self.assertEqual(data["message"], "That's a question, not a goal. HADES executes goals.")
        self.assertEqual(data["examples"], goal_compiler.EXAMPLE_GOALS)
        for example in data["examples"]:
            self.assertEqual(goal_compiler.classify_input(example)[0], "GOAL", example)

    def with_fake_llm(self, reply):
        calls = {"count": 0}

        def fake_gemini(prompt, grounded=False, on_request=None):
            calls["count"] += 1
            on_request("GEMINI")
            return reply, "GEMINI"

        originals = main.gemini, main.ai_enhancements_enabled
        main.gemini, main.ai_enhancements_enabled = fake_gemini, lambda: True
        return calls, originals

    def restore(self, originals):
        main.gemini, main.ai_enhancements_enabled = originals

    def test_llm_quick_answer_is_counted_separately(self):
        calls, originals = self.with_fake_llm('{"kind": "QUESTION", "answer": "Paris is the capital of France."}')
        before = dict(main.LLM_CALLS)
        try:
            data, created = self.plan("what is the capital of France?")
        finally:
            self.restore(originals)
        self.assertEqual(created, 0)
        self.assertEqual(data["classifier"], "llm")
        self.assertEqual(data["quick_answer"], "Paris is the capital of France.")
        self.assertEqual(data["quick_answer_label"], "Quick answer (not a mission)")
        self.assertEqual(main.LLM_CALLS["conversation"], before["conversation"] + 1)
        for phase in main.MISSION_LLM_PHASES:
            self.assertEqual(main.LLM_CALLS[phase], before[phase], phase)
        endpoint = TestClient(main.app).get("/llm-calls").json()
        self.assertEqual(endpoint["conversation"], main.LLM_CALLS["conversation"])
        self.assertNotIn("conversation", endpoint["totals"])

    def test_llm_cannot_reject_a_supported_goal(self):
        calls, originals = self.with_fake_llm('{"kind": "CHAT", "answer": "nope"}')
        try:
            result = main.classify_input(EXAM_GOAL)
        finally:
            self.restore(originals)
        self.assertEqual(result["kind"], "GOAL")
        self.assertEqual(calls["count"], 0)

    def test_invalid_llm_classification_falls_back_to_rules(self):
        calls, originals = self.with_fake_llm('{"kind": "MAYBE"}')
        try:
            result = main.classify_input("hi")
        finally:
            self.restore(originals)
        self.assertEqual((result["kind"], result["classifier"]), ("CHAT", "rules"))


class ExamDecompositionTests(unittest.TestCase):

    def test_exam_goal_requirements(self):
        result = goal_compiler.decompose_goal(EXAM_GOAL, today=FRIDAY)
        self.assertEqual(result["domain"], "exam")
        specs = {spec["type"]: spec for spec in result["requirements"]}
        self.assertEqual(list(specs), ["study_schedule", "study_calendar", "revision_checklist"])
        self.assertEqual(specs["study_schedule"]["parameters"], {"subject": "Physics", "exam_date": "2026-10-05"})
        self.assertEqual(specs["study_calendar"]["depends_on"], ["req_study_schedule"])
        self.assertEqual(
            [spec["verifier"] for spec in specs.values()],
            ["verify_study_schedule", "verify_study_calendar", "verify_revision_checklist"],
        )

    def test_unit_tests_are_not_an_exam(self):
        self.assertIsNone(goal_compiler.decompose_goal("write unit tests and prepare the release notes", today=FRIDAY))

    def test_subject_extraction(self):
        self.assertEqual(goal_compiler.extract_subject("help me revise for my maths exam"), "Mathematics")
        self.assertEqual(goal_compiler.extract_subject("prepare for my astronomy exam"), "Astronomy")

    def sessions(self, exam_date):
        syllabus = exam_tools.load_syllabus({"params": {"subject": "Physics"}})[1]
        return exam_tools.plan_study_sessions({
            "params": {"exam_date": exam_date},
            "upstream": {"load_syllabus": syllabus},
            "today": FRIDAY,
        })[1]["sessions"]

    def test_schedule_before_monday(self):
        sessions = self.sessions("2026-10-05")
        self.assertEqual([item["date"] for item in sessions], ["2026-10-03", "2026-10-04"])
        self.assertEqual({(item["start"], item["end"]) for item in sessions}, {("10:00", "12:00")})
        covered = [topic for item in sessions for topic in item["topics"]]
        self.assertEqual(covered, goal_compiler.load_syllabus()["subjects"]["Physics"]["topics"])

    def test_schedule_before_wednesday_has_revision_day(self):
        sessions = self.sessions("2026-10-07")
        self.assertEqual([item["date"] for item in sessions], ["2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06"])
        self.assertEqual(sessions[-1]["topics"], [exam_tools.FINAL_REVISION])
        self.assertEqual((sessions[2]["start"], sessions[2]["end"]), ("18:00", "20:00"))

    def test_exam_in_the_past_fails(self):
        with self.assertRaises(trip_tools.ToolError):
            self.sessions("2026-10-02")


def run_exam_mission(goal=EXAM_GOAL):
    client = TestClient(main.app)
    plan = client.post("/plan", json={"goal": goal}).json()["plan"]
    client.post("/execute-approved-stream", json={"goal": plan["goal"], "plan": plan, "approved": True})
    return main.MISSIONS[plan["id"]]


class ExamMissionTests(unittest.TestCase):

    def test_exam_mission_completes(self):
        mission = run_exam_mission()
        self.assertEqual(mission["contract"]["domain"], "exam")
        self.assertEqual(mission["contract"]["parameters"]["subject"], "Physics")
        self.assertEqual(mission["status"], "complete", [item["reason"] for item in mission["verification"]["requirement_results"]])
        results = mission["verification"]["requirement_results"]
        self.assertEqual([item["verifier"] for item in results], ["verify_study_schedule", "verify_study_calendar", "verify_revision_checklist"])
        latest = main.latest_evidence(mission)
        self.assertTrue(Path(latest["create_study_calendar"]["data"]["path"]).exists())
        self.assertTrue(Path(latest["build_revision_checklist"]["data"]["path"]).exists())
        self.assertIn("Physics exam prep", mission["artifacts"][-1])
        self.assertEqual(mission["llm_calls"], {"planning": 0, "execution": 0, "recovery": 0, "verification": 0})

    def test_exam_moved_to_wednesday(self):
        mission = run_exam_mission()
        before = {item["step"]: item["id"] for item in mission["evidence"]}
        response = TestClient(main.app).post(f"/mission/{mission['id']}/change", json={"text": "exam moved to Wednesday"})
        self.assertEqual(response.status_code, 200, response.text)
        change = dict(sse_events(response.text))["change"]["change"]
        wednesday = goal_compiler.resolve_weekday("wednesday", date.today()).isoformat()
        self.assertEqual(list(change["diff"]), ["exam_date"])
        self.assertEqual(change["diff"]["exam_date"]["after"], wednesday)
        self.assertEqual(change["message"], "Re-executing 2 of 5 tasks")
        self.assertEqual(change["rerun_steps"], ["plan_study_sessions", "create_study_calendar"])
        self.assertEqual(sorted(item["step"] for item in change["stale_evidence"]), ["create_study_calendar", "plan_study_sessions"])
        self.assertEqual(sorted(change["stale_requirements"]), ["req_study_calendar", "req_study_schedule"])

        mission = main.MISSIONS[mission["id"]]
        latest = main.latest_evidence(mission)
        for step_id in ("load_syllabus", "build_revision_checklist"):
            self.assertEqual(latest[step_id]["id"], before[step_id], f"{step_id} must not re-run")
        self.assertEqual(mission["status"], "complete")
        self.assertEqual(mission["contract"]["parameters"]["exam_date"], wednesday)
        sessions = latest["plan_study_sessions"]["data"]["sessions"]
        self.assertTrue(all(item["date"] < wednesday for item in sessions))
        self.assertIn(main.goal_compiler.date_label(wednesday), mission["contract"]["requirements"][0])

    def test_exam_change_rejects_trip_parameters(self):
        mission = run_exam_mission()
        response = TestClient(main.app).post(f"/mission/{mission['id']}/change", json={"changes": {"max_budget": 5000}})
        self.assertEqual(response.status_code, 400)
        self.assertIn("no max_budget", response.json()["detail"])

    def test_unknown_subject_uses_generic_outline(self):
        mission = run_exam_mission("prepare me for my astronomy exam on Monday")
        self.assertEqual(mission["status"], "complete", [item["reason"] for item in mission["verification"]["requirement_results"]])
        checklist = next(item for item in mission["verification"]["requirement_results"] if item["requirement_id"] == "req_revision_checklist")
        self.assertIn("generic outline", checklist["reason"])


class ExamVerifierTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mission = run_exam_mission()

    def check(self, requirement_type, mutate=None):
        evidence = json.loads(json.dumps(main.MISSIONS[self.mission["id"]]["evidence"]))
        latest = {item["step"]: item for item in evidence}
        if mutate:
            mutate(latest)
        result, _ = main.verify_typed(self.mission["contract"], evidence)
        return next(item for item in result["requirement_results"] if item["requirement_id"] == f"req_{requirement_type}")

    def assert_fails(self, requirement_type, mutate, fragment):
        result = self.check(requirement_type, mutate)
        self.assertEqual(result["status"], "missing")
        self.assertIn(fragment, result["reason"])

    def test_all_pass(self):
        for kind in ("study_schedule", "study_calendar", "revision_checklist"):
            self.assertEqual(self.check(kind)["status"], "satisfied", kind)

    def test_overlapping_sessions_fail(self):
        def overlap(latest):
            sessions = latest["plan_study_sessions"]["data"]["sessions"]
            sessions.append(dict(sessions[0], index=99, start="11:00", end="13:00"))
        self.assert_fails("study_schedule", overlap, "overlap")

    def test_session_on_exam_day_fails(self):
        exam_date = self.mission["contract"]["parameters"]["exam_date"]
        self.assert_fails("study_schedule", lambda latest: latest["plan_study_sessions"]["data"]["sessions"][0].update(date=exam_date), "is not before the exam")

    def test_uncovered_topic_fails(self):
        def drop(latest):
            for session in latest["plan_study_sessions"]["data"]["sessions"]:
                session["topics"] = [topic for topic in session["topics"] if topic != "Mechanics"]
        self.assert_fails("study_schedule", drop, "No session covers: Mechanics")

    def test_calendar_must_contain_every_session(self):
        path = Path(main.latest_evidence(self.mission)["create_study_calendar"]["data"]["path"])
        original = path.read_bytes()
        try:
            text = original.decode("utf-8")
            first_event = text.index("BEGIN:VEVENT")
            second_event = text.index("BEGIN:VEVENT", first_event + 1)
            path.write_bytes((text[:first_event] + text[second_event:]).encode("utf-8"))
            self.assert_fails("study_calendar", None, "is missing 1 of")
        finally:
            path.write_bytes(original)

    def test_checklist_must_match_subject(self):
        path = Path(main.latest_evidence(self.mission)["build_revision_checklist"]["data"]["path"])
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("Physics", "Chemistry", 1), encoding="utf-8")
            self.assert_fails("revision_checklist", None, "does not name Physics")
            path.write_text("# Physics revision checklist\n", encoding="utf-8")
            self.assert_fails("revision_checklist", None, "no checklist items")
        finally:
            path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
