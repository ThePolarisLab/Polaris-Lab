"""Aggregate diagnostics cannot reveal provider data or alter sync decisions."""
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
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


class UnprintableError(RuntimeError):
    def __str__(self):
        raise AssertionError("diagnostics must never stringify arbitrary exceptions")


class DiagnosticProvider:
    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, []

    def _request_json(self, path, *, params, operation):
        self.calls.append((path, params))
        if path == "/v1/vehicles/lookup":
            i = int(params["number"].rsplit("-", 1)[1])
            return {"vehicle": {"id": f"PRIVATE-PROVIDER-{i}", "number": f"PRIVATE-TRUCK-{i}",
                    "current_driver": {"id": "PRIVATE-DRIVER-ID", "first_name": "PRIVATE-DRIVER",
                                       "status": "active", "credentials": "PRIVATE-CREDENTIAL"}}}
        assert path == "/v3/vehicle_locations"
        i = int(params["vehicle_ids[]"].rsplit("-", 1)[1])
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
    assert set(value["unavailable_reason_counts"]) == set(sync.UNAVAILABLE_REASONS)
    assert set(value["requested_by_status"]) == set(value["unavailable_by_status"]) == set(sync.VEHICLE_STATUS_BUCKETS)
    encoded = json.dumps(value)
    assert not any(private in encoded for private in PRIVATE)


def test_repeatable_23_vehicle_aggregate_diagnostics_without_filtering(setup, caplog):
    # Deliberately include successful inactive vehicles and failed active ones.
    # Status bucketing diagnoses selection; it must never change that selection.
    outcomes = ["valid"] * 12 + list(sync.UNAVAILABLE_REASONS) + [
        "unknown_controlled_error", "location_contract_unavailable",
        "location_unavailable", "location_city_or_timestamp_unavailable",
    ]
    statuses = ["active", " INACTIVE ", "PRIVATE-STATUS"] * 7 + ["active", "inactive"]
    with setup["factory"].begin() as session:
        for i, status in enumerate(statuses):
            session.add(MotiveVehicleRecord(organization_id=setup["org"], organization_slug="mor-logistics",
                        provider_vehicle_id=f"PRIVATE-PROVIDER-{i}", unit_number=f"PRIVATE-TRUCK-{i}",
                        vin="PRIVATE-VIN", status=status))
    provider = DiagnosticProvider(outcomes)
    results = []
    for _ in range(2):
        with setup["factory"]() as session:
            value = sync.sync_locations(session, organization_id=setup["org"], connector=provider, now=NOW)
        assert_invariants(value)
        assert value["status"] == "degraded"
        assert (value["vehicles_requested"], value["locations_observed"], value["unavailable"]) == (23, 12, 11)
        assert value["requested_by_status"] == {"active": 8, "inactive": 8, "other_or_unknown": 7}
        assert value["unavailable_by_status"] == {"active": 4, "inactive": 4, "other_or_unknown": 3}
        assert value["unavailable_reason_counts"] == {
            "provider_request_failed": 1, "location_contract_unavailable": 2,
            "location_identity_mismatch": 1, "location_unavailable": 2,
            "location_coordinates_invalid": 1, "location_city_or_timestamp_unavailable": 2,
            "unexpected_unavailable": 2,
        }
        results.append(value)
    assert results[0] == results[1]
    assert len(provider.calls) == 2 * (23 + 12)
    with setup["factory"]() as session:
        assert session.query(MotiveLocationObservation).count() == 23
        assert session.query(MotiveLocationObservation).filter_by(signal_status="observed").count() == 12
        assert session.query(MotiveLocationObservation).filter_by(signal_status="unavailable").count() == 11
    assert not any(private in caplog.text for private in PRIVATE)


@pytest.mark.parametrize("status,bucket", [
    ("ACTIVE", "active"), (" in_service ", "active"), ("inactive", "inactive"),
    (" Deactivated ", "inactive"), ("out-of-service", "inactive"),
    (None, "other_or_unknown"), ("", "other_or_unknown"), ("PRIVATE-STATUS", "other_or_unknown"),
    (123, "other_or_unknown"),
])
def test_safe_status_normalization(status, bucket):
    assert sync._vehicle_status_bucket(status) == bucket


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
    assert provider.calls == []


def test_driver_lookup_failure_remains_observed_location(setup):
    with setup["factory"].begin() as session:
        session.add(MotiveVehicleRecord(organization_id=setup["org"], organization_slug="mor-logistics",
                    provider_vehicle_id="PRIVATE-PROVIDER-0", unit_number="PRIVATE-TRUCK-0", status="inactive"))
    class LookupFailure(DiagnosticProvider):
        def _request_json(self, path, **kwargs):
            if path == "/v1/vehicles/lookup":
                raise MotiveConnectorError("PRIVATE-EXCEPTION")
            return super()._request_json(path, **kwargs)
    with setup["factory"]() as session:
        value = sync.sync_locations(session, organization_id=setup["org"], connector=LookupFailure(["valid"]), now=NOW)
    assert_invariants(value)
    assert value["status"] == "success" and value["locations_observed"] == 1
    assert value["unavailable"] == 0  # existing _vehicle_lookup fallback is unchanged


def workflow_summary(payload, capsys):
    workflow = Path(__file__).resolve().parents[3] / ".github/workflows/motive-location-observations.yml"
    script = textwrap.dedent(workflow.read_text(encoding="utf-8").split("        run: |\n", 1)[1])
    # Execute the exact summary/failure tail without credentials or network.
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
        "status": status, "vehicles_requested": 23, "locations_observed": 12, "unavailable": 11,
        "as_of": NOW.isoformat(), "provider_payload": PRIVATE,
        "unavailable_reason_counts": {"location_unavailable": 11, "PRIVATE-PROVIDER": 1},
        "requested_by_status": {"active": 12, "inactive": 11, "PRIVATE-TRUCK": 23},
        "unavailable_by_status": {"inactive": 11, "PRIVATE-STATUS": 11},
    }
    summary, output, actual_failed = workflow_summary(payload, capsys)
    assert actual_failed is failed
    assert not any(private in output for private in PRIVATE)
    assert set(summary) == {"status", "vehicles_requested", "locations_observed", "unavailable", "as_of",
                            "unavailable_reason_counts", "requested_by_status", "unavailable_by_status"}
    assert summary["unavailable_reason_counts"] == {"location_unavailable": 11}
    assert sum(summary["requested_by_status"].values()) == 23
    assert sum(summary["unavailable_by_status"].values()) == 11


def test_workflow_rejects_sensitive_strings_in_whitelisted_fields(capsys):
    payload = {"status": "degraded", "vehicles_requested": "PRIVATE-PROVIDER", "unavailable": True,
               "locations_observed": ["PRIVATE-TRUCK"], "as_of": "PRIVATE-EXCEPTION PRIVATE-CREDENTIAL",
               "unavailable_reason_counts": {key: "PRIVATE-PAYLOAD" for key in sync.UNAVAILABLE_REASONS},
               "requested_by_status": {"active": "PRIVATE-DRIVER", "inactive": -1},
               "unavailable_by_status": {"inactive": {"city": "PrivateCity"}}}
    summary, output, failed = workflow_summary(payload, capsys)
    assert failed and not any(private in output for private in PRIVATE)
    assert summary["as_of"] is None and summary["vehicles_requested"] is None
    assert summary["unavailable_reason_counts"] == summary["requested_by_status"] == summary["unavailable_by_status"] == {}
