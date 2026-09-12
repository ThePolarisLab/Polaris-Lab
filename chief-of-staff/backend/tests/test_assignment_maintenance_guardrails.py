from __future__ import annotations

from app.api.assignment_guardrails import apply_maintenance_guardrails


def _response():
    return {
        "truck_candidates": [
            {"truck_number": "M2209", "dispatch_readiness": {"classification": "ready", "verification_required": False, "hard_blockers": [], "verification_reasons": []}},
            {"truck_number": "M2210", "dispatch_readiness": {"classification": "verify", "verification_required": True, "hard_blockers": [], "verification_reasons": ["location_stale_or_missing"]}},
            {"truck_number": "M2201", "dispatch_readiness": {"classification": "ready", "verification_required": False, "hard_blockers": [], "verification_reasons": []}},
        ],
        "decision_guardrails": {"dispatcher_approval_required": True, "autonomous_assignment_performed": False},
        "provider_calls": {"motive_latest_location": True},
    }


def test_maintenance_verify_downgrades_ready_candidate():
    response = _response()
    maintenance = {
        "as_of_date": "2026-09-12",
        "fault_codes_available": True,
        "fault_codes_window_complete": True,
        "inspection_reports_available": True,
        "inspection_reports_window_complete": True,
        "classifications": [
            {"truck_number": "M2209", "classification": "verify", "hard_blockers": [], "verification_reasons": ["opened_fault_code_present"]},
            {"truck_number": "M2210", "classification": "not_suitable", "hard_blockers": ["inspection_report_rejected"], "verification_reasons": []},
            {"truck_number": "M2201", "classification": "clear", "hard_blockers": [], "verification_reasons": []},
        ],
    }
    result = apply_maintenance_guardrails(response, maintenance)
    trucks = {row["truck_number"]: row for row in result["truck_candidates"]}

    assert trucks["M2209"]["dispatch_readiness"]["classification"] == "verify"
    assert "maintenance_opened_fault_code_present" in trucks["M2209"]["dispatch_readiness"]["verification_reasons"]
    assert trucks["M2210"]["dispatch_readiness"]["classification"] == "not_suitable"
    assert "maintenance_inspection_report_rejected" in trucks["M2210"]["dispatch_readiness"]["hard_blockers"]
    assert trucks["M2201"]["dispatch_readiness"]["classification"] == "ready"
    assert result["maintenance_readiness_summary"]["clear"] == 1
    assert result["maintenance_readiness_summary"]["verify"] == 1
    assert result["maintenance_readiness_summary"]["not_suitable"] == 1
    assert result["decision_guardrails"]["maintenance_fault_severity_used_as_hard_blocker"] is False
    assert result["decision_guardrails"]["maintenance_rejected_inspection_is_hard_blocker"] is True
    assert result["decision_guardrails"]["dispatcher_approval_required"] is True
    assert result["decision_guardrails"]["autonomous_assignment_performed"] is False
    assert result["provider_calls"]["motive_fault_codes"] is True
    assert result["provider_calls"]["motive_inspection_reports"] is True
