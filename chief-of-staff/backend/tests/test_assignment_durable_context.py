from copy import deepcopy

from app.api.assignment_guardrails import apply_durable_maintenance_context


def test_durable_context_is_advisory_only():
    response = {
        "truck_candidates": [
            {
                "truck_number": "M2214",
                "dispatch_readiness": {
                    "classification": "verify",
                    "verification_required": True,
                    "hard_blockers": [],
                    "verification_reasons": ["maintenance_open_inspection_part_present"],
                },
            },
            {
                "truck_number": "M2209",
                "dispatch_readiness": {
                    "classification": "ready",
                    "verification_required": False,
                    "hard_blockers": [],
                    "verification_reasons": [],
                },
            },
        ],
        "decision_guardrails": {},
    }
    before_order = [row["truck_number"] for row in response["truck_candidates"]]
    before_readiness = deepcopy(response["truck_candidates"][0]["dispatch_readiness"])
    memory = {
        "m2214": [{
            "truck_number": "M2214",
            "part_category": "18 - Lamps/Reflectors",
            "part_type": "minor",
            "part_name": None,
            "lifecycle_state": "open",
            "first_open_date": "2026-09-07",
            "last_seen_date": "2026-09-12",
            "last_seen_at": "2026-09-12T17:20:17+00:00",
            "last_odometer": 693506,
            "explicit_resolution_status": None,
            "explicit_resolution_date": None,
            "last_reopened_date": None,
            "reopen_count": 0,
            "open_observation_count": 6,
            "source_window_days": 7,
            "disappearance_means_resolved": False,
        }]
    }

    result = apply_durable_maintenance_context(response, memory)
    m2214 = result["truck_candidates"][0]
    issue = m2214["durable_maintenance_context"]["issues"][0]

    assert [row["truck_number"] for row in result["truck_candidates"]] == before_order
    assert m2214["dispatch_readiness"] == before_readiness
    assert issue["recurring"] is True
    assert issue["unresolved"] is True
    assert "First observed 2026-09-07" in issue["dispatcher_summary"]
    assert "6 open observations" in issue["dispatcher_summary"]
    assert result["durable_maintenance_memory_summary"]["unresolved_issue_count"] == 1
    assert result["decision_guardrails"]["durable_maintenance_memory_changes_readiness"] is False
    assert result["decision_guardrails"]["durable_maintenance_memory_changes_ranking"] is False
