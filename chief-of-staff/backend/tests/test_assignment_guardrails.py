from __future__ import annotations

from copy import deepcopy
from datetime import date

from app.api.assignment_guardrails import (
    apply_assignment_guardrails,
    classify_assignment_consistency,
    classify_pickup_temporal_status,
)


def _response(*, pickup_date: str = "2026-09-11", status: str = "assigned") -> dict:
    return {
        "load": {
            "status": status,
            "current_assignment": {"driver_name": "", "truck_number": "", "trailer_number": ""},
            "pickup": {"scheduled_date": pickup_date, "scheduled_time": "08:30"},
        },
        "truck_candidates": [
            {
                "truck_number": "M2209",
                "dispatch_readiness": {
                    "classification": "ready",
                    "verification_required": False,
                    "hard_blockers": [],
                    "verification_reasons": [],
                },
            },
            {
                "truck_number": "M2210",
                "dispatch_readiness": {
                    "classification": "not_suitable",
                    "verification_required": True,
                    "hard_blockers": ["motive_dispatch_availability_out_of_service"],
                    "verification_reasons": [],
                },
            },
        ],
        "readiness_summary": {
            "ready": 1,
            "verify": 0,
            "not_suitable": 1,
            "top_ranked_truck_readiness": "ready",
        },
        "decision_guardrails": {"dispatcher_approval_required": True},
    }


def test_past_pickup_is_calendar_date_only_and_does_not_claim_overdue_timezone_semantics() -> None:
    result = classify_pickup_temporal_status("2026-09-11", reference_date=date(2026, 9, 12))

    assert result["status"] == "past"
    assert result["days_from_reference"] == -1
    assert result["comparison_basis"] == "calendar_date_only"
    assert result["pickup_timezone_certified"] is False
    assert result["appointment_overdue_confirmed"] is False


def test_future_and_same_day_pickups_are_distinguished_without_time_of_day_guessing() -> None:
    assert classify_pickup_temporal_status("2026-09-13", reference_date=date(2026, 9, 12))["status"] == "upcoming"
    assert classify_pickup_temporal_status("2026-09-12", reference_date=date(2026, 9, 12))["status"] == "today"
    assert classify_pickup_temporal_status("not-a-date", reference_date=date(2026, 9, 12))["status"] == "unknown"


def test_assigned_without_driver_truck_or_trailer_is_flagged_as_inconsistent() -> None:
    result = classify_assignment_consistency(
        "assigned",
        {"driver_name": "", "truck_number": None, "trailer_number": "   "},
    )

    assert result["consistent"] is False
    assert result["classification"] == "assigned_without_assignment_details"
    assert result["missing_fields"] == ["driver_name", "truck_number", "trailer_number"]
    assert result["reason_codes"] == ["assigned_status_without_assignment_details"]


def test_assigned_partial_details_are_flagged_but_unassigned_blank_details_are_not() -> None:
    partial = classify_assignment_consistency(
        "assigned",
        {"driver_name": "Driver One", "truck_number": "", "trailer_number": "R1"},
    )
    unassigned = classify_assignment_consistency(
        "unassigned",
        {"driver_name": "", "truck_number": "", "trailer_number": ""},
    )

    assert partial["classification"] == "assigned_with_partial_assignment_details"
    assert partial["missing_fields"] == ["truck_number"]
    assert unassigned["consistent"] is True
    assert unassigned["missing_fields"] == []


def test_past_pickup_and_assignment_inconsistency_downgrade_ready_to_verify() -> None:
    result = apply_assignment_guardrails(deepcopy(_response()), reference_date=date(2026, 9, 12))

    first = result["truck_candidates"][0]["dispatch_readiness"]
    second = result["truck_candidates"][1]["dispatch_readiness"]

    assert first["classification"] == "verify"
    assert first["verification_required"] is True
    assert "pickup_date_past" in first["verification_reasons"]
    assert "assigned_status_without_assignment_details" in first["verification_reasons"]
    assert second["classification"] == "not_suitable"
    assert result["readiness_summary"] == {
        "ready": 0,
        "verify": 1,
        "not_suitable": 1,
        "top_ranked_truck_readiness": "verify",
    }
    assert result["decision_guardrails"]["past_pickup_requires_dispatch_verification"] is True
    assert result["decision_guardrails"]["assignment_data_inconsistency_present"] is True
    assert result["decision_guardrails"]["dispatcher_approval_required"] is True


def test_upcoming_consistent_load_does_not_change_existing_readiness() -> None:
    response = _response(pickup_date="2026-09-13")
    response["load"]["current_assignment"] = {
        "driver_name": "Driver One",
        "truck_number": "M2209",
        "trailer_number": "R1",
    }

    result = apply_assignment_guardrails(response, reference_date=date(2026, 9, 12))

    assert result["truck_candidates"][0]["dispatch_readiness"]["classification"] == "ready"
    assert result["readiness_summary"]["ready"] == 1
    assert result["load_guardrails"]["pickup_temporal"]["status"] == "upcoming"
    assert result["load_guardrails"]["assignment_consistency"]["consistent"] is True
