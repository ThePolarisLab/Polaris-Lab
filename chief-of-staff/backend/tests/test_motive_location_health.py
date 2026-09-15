"""Motive location sync health is distinct from per-vehicle GPS coverage."""
from datetime import datetime, timezone

from app.connectors.motive import MotiveConnectorError
from app.models.motive import MotiveVehicleRecord
from app.models.motive_location import MotiveLocationObservation
from app.motive import location_sync as sync
from tests.test_chatgpt_mcp import setup, keys

NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


class HealthProvider:
    def __init__(self, outcomes, *, v2_candidates=None):
        self.outcomes = outcomes
        self.v2_candidates = set(v2_candidates or ())

    @staticmethod
    def _index(params):
        value = params.get("vehicle_ids[]") or params.get("number")
        return int(str(value).rsplit("-", 1)[1])

    def _request_json(self, path, *, params, operation):
        index = self._index(params)
        provider_id = f"provider-{index}"
        unit_number = f"truck-{index}"
        if path == "/v1/vehicles/lookup":
            return {"vehicle": {"id": provider_id, "number": unit_number}}
        if path == "/v2/vehicle_locations":
            if index not in self.v2_candidates:
                return {"vehicles": []}
            return {"vehicles": [{
                "id": provider_id,
                "number": unit_number,
                "current_location": {"lat": 49.89, "lon": -97.13},
            }]}
        assert path == "/v3/vehicle_locations"
        outcome = self.outcomes[index]
        if outcome == "provider_failure":
            raise MotiveConnectorError("private provider failure")
        if outcome == "zero_rows":
            return {"vehicles": []}
        vehicle = {
            "id": provider_id,
            "number": unit_number,
            "current_location": {
                "lat": 49.89,
                "lon": -97.13,
                "city": "Winnipeg",
                "state": "MB",
                "located_at": NOW.isoformat(),
            },
        }
        if outcome == "no_current_location":
            vehicle.pop("current_location")
        return {"vehicles": [{"vehicle": vehicle}]}


def add_vehicles(setup, statuses):
    with setup["factory"].begin() as session:
        for index, status in enumerate(statuses):
            session.add(MotiveVehicleRecord(
                organization_id=setup["org"],
                organization_slug="mor-logistics",
                provider_vehicle_id=f"provider-{index}",
                unit_number=f"truck-{index}",
                status=status,
            ))


def test_normal_missing_gps_is_partial_evidence_but_healthy_sync(setup):
    add_vehicles(setup, ["active"] * 14 + ["inactive"] * 9)
    provider = HealthProvider(["valid"] * 12 + ["zero_rows"] * 2)

    with setup["factory"]() as session:
        value = sync.sync_locations(
            session, organization_id=setup["org"], connector=provider, now=NOW
        )

    assert value["status"] == "success"
    assert value["evidence_status"] == "partial"
    assert value["blocking_unavailable"] == 0
    assert value["vehicles_known"] == 23
    assert value["vehicles_requested"] == 14
    assert value["locations_observed"] == 12
    assert value["unavailable"] == 2
    assert value["vehicles_skipped"] == value["inactive_skipped"] == 9
    assert value["unavailable_reason_counts"]["location_unavailable"] == 2
    assert value["unavailable_reason_counts"]["location_contract_unavailable"] == 0

    with setup["factory"]() as session:
        assert session.query(MotiveLocationObservation).filter_by(signal_status="observed").count() == 12
        unavailable = session.query(MotiveLocationObservation).filter_by(signal_status="unavailable").all()
        assert len(unavailable) == 2
        assert all(row.city is None and row.location_observed_at is None for row in unavailable)


def test_v2_candidate_keeps_v3_contract_gap_system_degraded(setup):
    add_vehicles(setup, ["active"])
    provider = HealthProvider(["zero_rows"], v2_candidates={0})

    with setup["factory"]() as session:
        value = sync.sync_locations(
            session, organization_id=setup["org"], connector=provider, now=NOW
        )

    assert value["status"] == "degraded"
    assert value["evidence_status"] == "partial"
    assert value["blocking_unavailable"] == 1
    assert value["unavailable_reason_counts"]["location_contract_unavailable"] == 1


def test_provider_failure_remains_system_degraded(setup):
    add_vehicles(setup, ["active"])
    provider = HealthProvider(["provider_failure"])

    with setup["factory"]() as session:
        value = sync.sync_locations(
            session, organization_id=setup["org"], connector=provider, now=NOW
        )

    assert value["status"] == "degraded"
    assert value["evidence_status"] == "partial"
    assert value["blocking_unavailable"] == 1
    assert value["unavailable_reason_counts"]["provider_request_failed"] == 1


def test_full_active_coverage_is_complete_healthy_sync(setup):
    add_vehicles(setup, ["active", "active"])
    provider = HealthProvider(["valid", "valid"])

    with setup["factory"]() as session:
        value = sync.sync_locations(
            session, organization_id=setup["org"], connector=provider, now=NOW
        )

    assert value["status"] == "success"
    assert value["evidence_status"] == "complete"
    assert value["blocking_unavailable"] == 0
    assert value["unavailable"] == 0
