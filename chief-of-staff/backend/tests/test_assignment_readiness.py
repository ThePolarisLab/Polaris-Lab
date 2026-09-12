from __future__ import annotations

from app.api.assignment_intelligence import _classify_dispatch_readiness


def _candidate(**overrides):
    candidate = {
        "vehicle_status": "active",
        "distance_to_pickup_km": 12.2,
        "location_stale": False,
        "dispatch_availability_status": "in_service",
        "current_driver_authoritative": True,
        "current_driver": {"name": "Driver Ready", "status": "active"},
        "current_driver_hos_observed": {
            "hos_date": "2026-09-12",
            "driving_duration_seconds": 1200,
            "is_legal_remaining_hours": False,
        },
    }
    candidate.update(overrides)
    return candidate


def test_dispatch_readiness_ready_requires_complete_certified_signals() -> None:
    readiness = _classify_dispatch_readiness(_candidate())

    assert readiness["classification"] == "ready"
    assert readiness["verification_required"] is False
    assert readiness["hard_blockers"] == []
    assert readiness["verification_reasons"] == []
    assert readiness["distance_to_pickup_km"] == 12.2
    assert readiness["distance_threshold_applied"] is False
    assert readiness["legal_remaining_hos_confirmed"] is False
    assert readiness["dispatcher_approval_required"] is True


def test_dispatch_readiness_verify_when_location_is_stale() -> None:
    readiness = _classify_dispatch_readiness(_candidate(location_stale=True))

    assert readiness["classification"] == "verify"
    assert readiness["verification_required"] is True
    assert "location_stale_or_missing" in readiness["verification_reasons"]
    assert readiness["hard_blockers"] == []


def test_dispatch_readiness_verify_when_pairing_or_hos_is_missing() -> None:
    readiness = _classify_dispatch_readiness(
        _candidate(
            current_driver_authoritative=False,
            current_driver={"name": None, "status": None},
            current_driver_hos_observed=None,
        )
    )

    assert readiness["classification"] == "verify"
    assert "authoritative_current_driver_missing" in readiness["verification_reasons"]
    assert "paired_driver_hos_observation_missing" in readiness["verification_reasons"]


def test_dispatch_readiness_not_suitable_when_motive_marks_out_of_service() -> None:
    readiness = _classify_dispatch_readiness(
        _candidate(dispatch_availability_status="out_of_service")
    )

    assert readiness["classification"] == "not_suitable"
    assert readiness["verification_required"] is True
    assert readiness["hard_blockers"] == ["motive_dispatch_availability_out_of_service"]


def test_dispatch_readiness_not_suitable_when_authoritative_driver_inactive() -> None:
    readiness = _classify_dispatch_readiness(
        _candidate(current_driver={"name": "Driver Inactive", "status": "inactive"})
    )

    assert readiness["classification"] == "not_suitable"
    assert "authoritative_current_driver_not_active" in readiness["hard_blockers"]
