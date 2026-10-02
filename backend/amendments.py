"""Contract amendment proposals for HADES.

When a requirement fails because a contract constraint cannot be met (rather
than because a tool misbehaved), retrying inside the contract cannot help.
These proposers return structured before -> after diffs a human can approve.
Options are derived from the same local data the verifiers use, never from
the failing tool's own output.
"""

from datetime import datetime

import trip_tools


def budget_options(contract, spec):
    parameters = contract.get("parameters", {})
    limit = spec["parameters"].get("max_budget")
    trip_date = spec["parameters"].get("trip_date")
    mode = parameters.get("travel_mode") or "train"
    try:
        _, route, weekday, options = trip_tools.fare_options(
            parameters.get("destination"),
            datetime.strptime(trip_date, "%Y-%m-%d").date(),
        )
    except (trip_tools.ToolError, ValueError, TypeError):
        return []

    local = sum(item["amount"] for item in route["local_expenses"])

    def total(option):
        return option["outbound"] + option["return"] + local

    current = next((option for option in options if option["mode"] == mode), None)
    if not current or limit is None or total(current) <= limit:
        # The plan fits the budget, so the failure is not a constraint
        # problem; a plain retry is the right recovery.
        return []

    proposals = [{
        "id": "raise_budget",
        "requirement_id": spec["id"],
        "label": f"Raise budget to ₹{total(current):,}",
        "effect": f"Keep the {current['service']} on {weekday.title()}; total ₹{total(current):,}.",
        "diff": {"max_budget": {"before": limit, "after": total(current)}},
    }]
    for option in sorted(options, key=total):
        if option["mode"] != mode and total(option) <= limit:
            proposals.append({
                "id": f"switch_to_{option['mode']}",
                "requirement_id": spec["id"],
                "label": f"Switch to {option['service'].lower()} ({option['departure']}), ₹{total(option):,} total",
                "effect": f"Total ₹{total(option):,}, within the ₹{limit:,} limit.",
                "diff": {"travel_mode": {"before": mode, "after": option["mode"]}},
            })
    return proposals


PROPOSERS = {
    "budget": budget_options,
}


def propose(contract, verification):
    """Amendment options for every failed requirement whose failure is a
    contract constraint. Empty when retrying inside the contract is the fix."""
    specs = {spec["id"]: spec for spec in contract.get("requirement_specs", [])}
    options = []
    for result in (verification or {}).get("requirement_results", []):
        if result.get("status") == "satisfied":
            continue
        spec = specs.get(result.get("requirement_id"))
        proposer = PROPOSERS.get((spec or {}).get("type"))
        if proposer:
            options.extend(proposer(contract, spec))
    return options
