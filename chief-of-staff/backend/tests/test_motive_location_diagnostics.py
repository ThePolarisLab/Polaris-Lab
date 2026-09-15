"""Aggregate diagnostics cannot reveal provider data or alter evidence boundaries."""
from datetime import datetime, timezone
import json
from pathlib import Path
import textwrap

import pytest

from app.connectors.motive import MotiveConnectorError
from app.models.motive import MotiveVehicleRecord
from app.models.motive_location import MotiveLocationObservation
from app.motive import location_sync as sync
from tests.test_chatgpt_mcp import setup, keys

PRIVATE = ("PRIVATE-PROVIDER", "PRIVATE-TRUCK", "PRIVATE-VIN", "PRIVATE-DRIVER",
           "PrivateCity", "49.891234", "-97.131234", "PRIVATE-PAYLOAD",
           "PRIVATE-EXCEPTION", "PRIVATE-CREDENTIAL", "PRIVATE-STATUS")
NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


class UnprintableError(RuntimeError):
    def __str__(self):
        raise AssertionError("diagnostics must never stringify arbitrary exceptions")


class DiagnosticProvider:
    def __init__(self, outcomes, v2_candidates=None):
        self.outcomes = outcomes
        self.v2_candidates = set(v2_candidates or ())
        self.calls = []

    def _index(self, params):
        value = params.get("vehicle_ids[]") or params.get("number")
        return int(str(value).rsplit("-", 1)[1])

    def _request_json(self, path, *, params, operation):
        self.calls.append((path, params, operation))
        i = self._index(params)
        if path == "/v1/vehicles/lookup":
            return {"vehicle": {"id": f"PRIVATE-PROVIDER-{i}", "number": f"PRIVATE-TRUCK-{i}",
                    "current_driver": {"id": "PRIVATE-DRIVER-ID", "first_name": "PRIVATE-DRIVER",
                                       "status": "active", "credentials": "PRIVATE-CREDENTIAL"}}}
        if path == "/v2/vehicle_locations":
            if i not in self.v2_candidates:
                return {"vehicles": [], "raw": "PRIVATE-PAYLOAD"}
            return {"vehicles": [{
                "id": f"PRIVATE-PROVIDER-{i}", "number": f"PRIVATE-TRUCK-{i}",
                "current_location": {"lat": 49.891234, "lon": -97.131234,
                                     "description": "PrivateCity", "located_at": NOW.isoformat()},
                "raw": "PRIVATE-PAYLOAD",
            }]}
        assert path == "/v3/vehicle_locations"
        outcome = self.outcomes[i]
        if outcome == "provider_request_failed":
            raise MotiveConnectorError("PRIVATE-EXCEPTION PRIVATE-CREDENTIAL", code="PRIVATE-PAYLOAD")
        if outcome == "unexpected_unavailable":
            raise UnprintableError("PRIVATE-EXCEPTION")
        if outcome == "unknown_controlled_error":
            raise sync.LocationSyncError("location_unavailable PRIVATE-EXCEPTION")
        vehicle = {"id": f"PRIVATE-PROVIDER-{i}", "number": f"PRIVATE-TRUCK-{i}",
                   "vin": "PRIVATE-VIN", "provider_payload": "PRIVATE-PAYLOAD",
                   "current_location": {"lat": 49.891234, "lon": -97.131234, "city": "PrivateCity",
                                        "state": "MB", "located_at": NOW.isoformat()}}
        if outcome == "location_contract_unavailable":
            return {"vehicles": [], "raw": "PRIVATE-PAYLOAD"}
        if outcome == "location_identity_mismatch":
            vehicle["id"] = "PRIVATE-PROVIDER-WRONG"
        if outcome == "location_unavailable":
            vehicle.pop("current_location")
        if outcome == "location_coordinates_invalid":
            vehicle["current_location"]["lat"] = 100
        if outcome == "location_city_or_timestamp_unavailable":
            vehicle["current_location"]["city"] = None
        return {"vehicles": [{"vehicle": vehicle}]}


def assert_invariants(value):
    assert sum(value["unavailable_reason_counts"].values()) == value["unavailable"]
    assert sum(value["requested_by_status"].values()) == value["vehicles_requested"]
    assert sum(value["unavailable_by_status"].values()) == value["unavailable"]
    assert sum(value["skipped_by_status"].values()) == value["vehicles_skipped"]
    assert value["vehicles_known"] == value["vehicles_requested"] + value["vehicles_skipped"]
    assert value["inactive_skipped"] == value["skipped_by_status"]["inactive"]
    assert set(value["unavailable_reason_counts"]) == set(sync.UNAVAILABLE_REASONS)
    assert set(value["requested_by_status"]) == set(value["unavailable_by_status"]) == set(value["skipped_by_status"]) == set(sync.VEHICLE_STATUS_BUCKETS)
    encoded = json.dumps(value)
    assert not any(private in encoded for private in PRIVATE)


def test_active_only_selection_skips_nine_inactive_and_keeps_two_active_zero_rows_degraded(setup, caplog):
    statuses = ["active"] * 14 + ["inactive"] * 9
    outcomes = ["valid"] * 12 + ["location_contract_unavailable"] * 2
    provider = DiagnosticProvider(outcomes, v2_candidates={12, 13})
    with setup["factory"].begin() as session:
        for i, status in enumerate(statuses):
            session.add(MotiveVehicleRecord(
                organization_id=setup["org"], organization_slug="mor-logistics",
                provider_vehicle_id=f"PRIVATE-PROVIDER-{i}", unit_number=f"PRIVATE-TRUCK-{i}",
                vin="PRIVATE-VIN", status=status,
            ))

    with setup["factory"]() as session:
        value = sync.sync_locations(session, organization_id=setup["org"], connector=provider, now=NOW)

    assert_invariants(value)
    assert value["status"] == "degraded"
    assert value["vehicles_known"] == 23
    assert (value["vehicles_requested"], value["locations_observed"], value["unavailable"]) == (14, 12, 2)
    assert value["vehicles_skipped"] == value["inactive_skipped"] == 9
    assert value["requested_by_status"] == {"active": 14, "inactive": 0, "other_or_unknown": 0}
    assert value["unavailable_by_status"] == {"active": 2, "inactive": 0, "other_or_unknown": 0}
    assert value["skipped_by_status"] == {"active": 0, "inactive": 9, "other_or_unknown": 0}
    assert value["unavailable_reason_counts"]["location_contract_unavailable"] == 2
    assert sum(value["unavailable_reason_counts"].values()) == 2

    v3_ids = {params["vehicle_ids[]"] for path, params, _ in provider.calls if path == "/v3/vehicle_locations"}
    assert v3_ids == {f"PRIVATE-PROVIDER-{i}" for i in range(14)}
    v2_ids = {params["vehicle_ids[]"] for path, params, _ in provider.calls if path == "/v2/vehicle_locations"}
    assert v2_ids == {"PRIVATE-PROVIDER-12", "PRIVATE-PROVIDER-13"}

    with setup["factory"]() as session:
        assert session.query(MotiveLocationObservation).count() == 23
        assert session.query(MotiveLocationObservation).filter_by(signal_status="observed").count() == 12
        assert session.query(MotiveLocationObservation).filter_by(signal_status="unavailable").count() == 2
        assert session.query(MotiveLocationObservation).filter_by(signal_status="inactive_skipped").count() == 9
    assert not any(private in caplog.text for private in PRIVATE)


def test_v2_probe_is_diagnostic_only_and_never_promotes_location_evidence(setup):
    with setup["factory"].begin() as session:
        session.add(MotiveVehicleRecord(
            organization_id=setup["org"], organization_slug="mor-logistics",
            provider_vehicle_id="PRIVATE-PROVIDER-0", unit_number="PRIVATE-TRUCK-0", status="active",
        ))
    provider = DiagnosticProvider(["location_contract_unavailable"], v2_candidates={0})
    with setup["factory"]() as session:
        value = sync.sync_locations(session, organization_id=setup["org"], connector=provider, now=NOW)
    assert value["status"] == "degraded"
    assert value["unavailable_reason_counts"]["location_contract_unavailable"] == 1
    with setup["factory"]() as session:
        observation = session.query(MotiveLocationObservation).one()
        assert observation.signal_status == "unavailable"
        assert observation.city is None and observation.location_observed_at is None


def test_v3_zero_and_v2_zero_is_true_location_unavailable(setup):
    with setup["factory"].begin() as session:
        session.add(MotiveVehicleRecord(
            organization_id=setup["org"], organization_slug="mor-logistics",
            provider_vehicle_id="PRIVATE-PROVIDER-0", unit_number="PRIVATE-TRUCK-0", status="active",
        ))
    provider = DiagnosticProvider(["location_contract_unavailable"])
    with setup["factory"]() as session:
        value = sync.sync_locations(session, organization_id=setup["org"], connector=provider, now=NOW)
    assert value["unavailable_reason_counts"]["location_contract_unavailable"] == 0
    assert value["unavailable_reason_counts"]["location_unavailable"] == 1


def test_inactive_and_unknown_status_invalidate_prior_location_without_provider_calls(setup):
    with setup["factory"].begin() as session:
        inactive = MotiveVehicleRecord(
            organization_id=setup["org"], organization_slug="mor-logistics",
            provider_vehicle_id="PRIVATE-PROVIDER-0", unit_number="PRIVATE-TRUCK-0", status="inactive",
        )
        unknown = MotiveVehicleRecord(
            organization_id=setup["org"], organization_slug="mor-logistics",
            provider_vehicle_id="PRIVATE-PROVIDER-1", unit_number="PRIVATE-TRUCK-1", status="PRIVATE-STATUS",
        )
        session.add_all([inactive, unknown])
        session.flush()
        for vehicle in (inactive, unknown):
            session.add(MotiveLocationObservation(
                organization_id=setup["org"], vehicle_id=vehicle.id, truck_number=vehicle.unit_number,
                city="PrivateCity", province="MB", country="Canada", location_observed_at=NOW,
                current_driver_name="PRIVATE-DRIVER", pairing_observed_at=NOW,
                collected_at=NOW.replace(hour=11), signal_status="observed",
            ))
    provider = DiagnosticProvider([])
    with setup["factory"]() as session:
        value = sync.sync_locations(session, organization_id=setup["org"], connector=provider, now=NOW)
    assert value["status"] == "success" and value["vehicles_requested"] == 0
    assert value["skipped_by_status"] == {"active": 0, "inactive": 1, "other_or_unknown": 1}
    assert provider.calls == []
    with setup["factory"]() as session:
        rows = session.query(MotiveLocationObservation).order_by(MotiveLocationObservation.vehicle_id).all()
        assert [row.signal_status for row in rows] == ["inactive_skipped", "status_unconfirmed_skipped"]
        assert all(row.city is None and row.location_observed_at is None and row.current_driver_name is None for row in rows)


@pytest.mark.parametrize("status,bucket", [
    ("ACTIVE", "active"), (" in_service ", "active"), ("inactive", "inactive"),
    (" Deactivated ", "inactive"), ("out-of-service", "inactive"),
    (None, "other_or_unknown"), ("", "other_or_unknown"), ("PRIVATE-STATUS", "other_or_unknown"),
    (123, "other_or_unknown"),
])
def test_safe_status_normalization(status, bucket):
    assert sync._vehicle_status_bucket(status) == bucket


@pytest.mark.parametrize("payload,expected", [
    ({"vehicles": [{"id": "PRIVATE-PROVIDER-0", "number": "PRIVATE-TRUCK-0", "current_location": {}}]}, True),
    ({"vehicles": []}, False),
    ({"vehicles": [{"id": "PRIVATE-PROVIDER-X", "number": "PRIVATE-TRUCK-0", "current_location": {}}]}, False),
    ({"vehicles": [{"id": "PRIVATE-PROVIDER-0", "number": "PRIVATE-TRUCK-0"}]}, False),
])
def test_v2_candidate_validation_is_structural_only(payload, expected):
    assert sync._v2_location_candidate(payload, "PRIVATE-PROVIDER-0", "PRIVATE-TRUCK-0") is expected


@pytest.mark.parametrize("error", [
    sync.LocationSyncError("PRIVATE-EXCEPTION"),
    sync.LocationSyncError("location_unavailable", "PRIVATE-EXCEPTION"),
    sync.LocationSyncError({"location_unavailable": "PRIVATE-EXCEPTION"}),
    UnprintableError("PRIVATE-EXCEPTION"),
])
def test_only_exact_whitelisted_controlled_errors_are_returned(error):
    assert sync._unavailable_reason(error) == "unexpected_unavailable"


def test_empty_fleet_has_zero_aggregate_counts_and_no_provider_calls(setup):
    provider = DiagnosticProvider([])
    with setup["factory"]() as session:
        value = sync.sync_locations(session, organization_id=setup["org"], connector=provider, now=NOW)
    assert_invariants(value)
    assert value["status"] == "success" and value["vehicles_requested"] == 0
    assert value["vehicles_known"] == value["vehicles_skipped"] == 0
    assert provider.calls == []


def test_driver_lookup_failure_remains_observed_location(setup):
    with setup["factory"].begin() as session:
        session.add(MotiveVehicleRecord(
            organization_id=setup["org"], organization_slug="mor-logistics",
            provider_vehicle_id="PRIVATE-PROVIDER-0", unit_number="PRIVATE-TRUCK-0", status="active",
        ))

    class LookupFailure(DiagnosticProvider):
        def _request_json(self, path, **kwargs):
            if path == "/v1/vehicles/lookup":
                raise MotiveConnectorError("PRIVATE-EXCEPTION")
            return super()._request_json(path, **kwargs)

    with setup["factory"]() as session:
        value = sync.sync_locations(session, organization_id=setup["org"], connector=LookupFailure(["valid"]), now=NOW)
    assert_invariants(value)
    assert value["status"] == "success" and value["locations_observed"] == 1
    assert value["unavailable"] == 0


def workflow_summary(payload, capsys):
    workflow = Path(__file__).resolve().parents[3] / ".github/workflows/motive-location-observations.yml"
    script = textwrap.dedent(workflow.read_text(encoding="utf-8").split("        run: |\n", 1)[1])
    tail = script[script.index("from datetime import datetime"):]
    failed = False
    try:
        exec(compile(tail, str(workflow), "exec"), {"payload": payload, "json": json})
    except SystemExit as exc:
        failed = exc.code != 0
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if line.startswith("Location sync summary: "))
    return json.loads(line.split(": ", 1)[1]), output, failed


@pytest.mark.parametrize("status,failed", [("success", False), ("degraded", True), ("PRIVATE-EXCEPTION", True)])
def test_workflow_prints_only_safe_fields_and_degraded_still_fails(status, failed, capsys):
    payload = {
        "status": status, "vehicles_known": 23, "vehicles_requested": 14, "locations_observed": 12,
        "unavailable": 2, "vehicles_skipped": 9, "inactive_skipped": 9, "as_of": NOW.isoformat(),
        "provider_payload": PRIVATE,
        "unavailable_reason_counts": {"location_contract_unavailable": 2, "PRIVATE-PROVIDER": 1},
        "requested_by_status": {"active": 14, "inactive": 0, "PRIVATE-TRUCK": 23},
        "unavailable_by_status": {"active": 2, "PRIVATE-STATUS": 11},
        "skipped_by_status": {"inactive": 9, "PRIVATE-DRIVER": 1},
    }
    summary, output, actual_failed = workflow_summary(payload, capsys)
    assert actual_failed is failed
    assert not any(private in output for private in PRIVATE)
    assert summary["unavailable_reason_counts"] == {"location_contract_unavailable": 2}
    assert sum(summary["requested_by_status"].values()) == 14
    assert sum(summary["unavailable_by_status"].values()) == 2


def test_workflow_rejects_sensitive_strings_in_whitelisted_fields(capsys):
    payload = {"status": "degraded", "vehicles_known": "PRIVATE-PROVIDER",
               "vehicles_requested": "PRIVATE-PROVIDER", "unavailable": True,
               "locations_observed": ["PRIVATE-TRUCK"], "vehicles_skipped": "PRIVATE-DRIVER",
               "inactive_skipped": -1, "as_of": "PRIVATE-EXCEPTION PRIVATE-CREDENTIAL",
               "unavailable_reason_counts": {key: "PRIVATE-PAYLOAD" for key in sync.UNAVAILABLE_REASONS},
               "requested_by_status": {"active": "PRIVATE-DRIVER", "inactive": -1},
               "unavailable_by_status": {"inactive": {"city": "PrivateCity"}},
               "skipped_by_status": {"inactive": "PRIVATE-TRUCK"}}
    summary, output, failed = workflow_summary(payload, capsys)
    assert failed and not any(private in output for private in PRIVATE)
    assert summary["as_of"] is None and summary["vehicles_requested"] is None
    assert summary["unavailable_reason_counts"] == summary["requested_by_status"] == summary["unavailable_by_status"] == {}
