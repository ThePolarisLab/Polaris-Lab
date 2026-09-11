from __future__ import annotations

from datetime import date, datetime, timezone
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import internal_motive
from app.database.database import SessionLocal
from app.main import app
from app.models.motive import MotiveVehicleRecord
from app.motive.assignment_signal_certification import certify_assignment_signal_schema
from app.security.job_auth import sign_job_request
from tests.auth_helpers import seed_principal

PATH = "/api/v1/internal/motive/assignment-signal-certification"
SECRET_ENV = "POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET"
ORG_ENV = "POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG"
SECRET = "motive-assignment-signal-certification-test-secret"
DAY = date(2026, 9, 10)


class FakeConnector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str]] = []

    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        self.calls.append((endpoint, params, operation))
        if endpoint == "/v1/hours_of_service":
            return {
                "hours_of_services": [
                    {
                        "hours_of_service": {
                            "id": 12,
                            "date": "2026-09-10",
                            "driving_duration": 7200,
                            "driver": {"id": 44, "status": "active", "first_name": "Synthetic"},
                        }
                    }
                ],
                "pagination": {"total": 1},
            }
        assert endpoint.startswith("/v3/vehicle_locations/")
        return {
            "vehicle_locations": [
                {
                    "id": "location-secret",
                    "located_at": "2026-09-10T12:00:00Z",
                    "lat": 49.89,
                    "lon": -97.13,
                    "speed": 80,
                }
            ]
        }


class EmptyThenLocationConnector(FakeConnector):
    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        self.calls.append((endpoint, params, operation))
        if endpoint == "/v1/hours_of_service":
            return {"hours_of_services": [], "pagination": {"total": 0}}
        if endpoint.endswith("provider-vehicle-1"):
            return {"vehicle_locations": []}
        if endpoint.endswith("provider-vehicle-2"):
            return {
                "vehicle_locations": [
                    {
                        "lat": 49.89,
                        "lon": -97.13,
                        "located_at": "2026-09-09T18:30:00Z",
                        "speed": 0,
                    }
                ]
            }
        raise AssertionError(f"unexpected extra provider call: {endpoint}")


class V1FallbackConnector(FakeConnector):
    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        self.calls.append((endpoint, params, operation))
        if endpoint == "/v1/hours_of_service":
            return {"hours_of_services": [], "pagination": {"total": 0}}
        if endpoint.startswith("/v3/vehicle_locations/"):
            return {"vehicle_locations": []}
        if endpoint == "/v1/vehicle_locations/provider-vehicle-1":
            return {}
        if endpoint == "/v1/vehicle_locations/provider-vehicle-2":
            return {
                "vehicle_location": {
                    "located_at": "2026-09-10T12:00:00Z",
                    "lat": 49.89,
                    "lon": -97.13,
                    "speed": 72,
                    "bearing": 180,
                }
            }
        raise AssertionError(f"unexpected extra provider call: {endpoint}")


def _signed_headers(*, body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Polaris-Job-Timestamp": timestamp,
        "X-Polaris-Job-Signature": sign_job_request(
            method="POST",
            path=PATH,
            body=body,
            timestamp=timestamp,
            secret=SECRET,
        ),
    }


def _add_vehicle(session, organization: dict[str, str], provider_vehicle_id: str, unit_number: str) -> None:
    session.add(
        MotiveVehicleRecord(
            organization_id=organization["id"],
            organization_slug=organization["slug"],
            provider_vehicle_id=provider_vehicle_id,
            source_endpoint="/v1/vehicles",
            unit_number=unit_number,
            status="active",
            observed_at=datetime.now(timezone.utc),
        )
    )


def test_schema_certification_returns_structure_only(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, _headers = seed_principal("owner")
    monkeypatch.setenv(ORG_ENV, organization["slug"])
    session = SessionLocal()
    try:
        _add_vehicle(session, organization, "provider-vehicle-secret", "M2209")
        session.commit()
        connector = FakeConnector()
        result = certify_assignment_signal_schema(session, certification_date=DAY, connector=connector)
    finally:
        session.close()

    assert result["status"] == "certification_completed"
    assert result["schema_values_returned"] is False
    assert result["raw_provider_payloads_returned"] is False
    assert result["driver_identity_values_returned"] is False
    assert result["vehicle_identity_values_returned"] is False
    assert result["coordinates_returned"] is False
    assert result["secrets_exposed"] is False

    hos = result["resources"]["hours_of_service"]
    location = result["resources"]["vehicle_location"]
    assert hos["available"] is True
    assert location["available"] is True
    assert location["non_empty_sample_found"] is True
    assert location["vehicles_examined"] == 1
    assert location["lookback_days"] == 7
    assert location["source_endpoint_version"] == "v3_history"
    assert location["v1_fallback_examined"] == 0
    assert "$.hours_of_services[].hours_of_service.driving_duration" in hos["observed_schema_paths"]
    assert "$.vehicle_locations[].lat" in location["observed_schema_paths"]
    serialized = repr(result)
    for forbidden in ("Synthetic", "provider-vehicle-secret", "M2209", "location-secret", "49.89", "-97.13"):
        assert forbidden not in serialized
    assert len(connector.calls) == 2
    assert connector.calls[0][0] == "/v1/hours_of_service"
    assert connector.calls[1][0].startswith("/v3/vehicle_locations/")
    assert connector.calls[1][1] == {"start_date": "2026-09-04", "end_date": "2026-09-10"}


def test_location_certification_scans_bounded_vehicles_until_non_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, _headers = seed_principal("owner")
    monkeypatch.setenv(ORG_ENV, organization["slug"])
    session = SessionLocal()
    try:
        _add_vehicle(session, organization, "provider-vehicle-1", "UNIT-1")
        _add_vehicle(session, organization, "provider-vehicle-2", "UNIT-2")
        _add_vehicle(session, organization, "provider-vehicle-3", "UNIT-3")
        session.commit()
        connector = EmptyThenLocationConnector()
        result = certify_assignment_signal_schema(session, certification_date=DAY, connector=connector)
    finally:
        session.close()

    location = result["resources"]["vehicle_location"]
    assert location["available"] is True
    assert location["non_empty_sample_found"] is True
    assert location["vehicles_examined"] == 2
    assert location["lookback_days"] == 7
    assert location["source_endpoint_version"] == "v3_history"
    assert location["v1_fallback_examined"] == 0
    assert "$.vehicle_locations[].located_at" in location["observed_schema_paths"]
    assert "$.vehicle_locations[].lat" in location["observed_schema_paths"]
    assert len(connector.calls) == 3
    assert connector.calls[1][0].endswith("provider-vehicle-1")
    assert connector.calls[2][0].endswith("provider-vehicle-2")
    assert all("provider-vehicle-3" not in call[0] for call in connector.calls)
    serialized = repr(result)
    for forbidden in ("provider-vehicle-1", "provider-vehicle-2", "UNIT-1", "UNIT-2", "49.89", "-97.13"):
        assert forbidden not in serialized


def test_location_certification_falls_back_to_v1_latest_without_leaking_values(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, _headers = seed_principal("owner")
    monkeypatch.setenv(ORG_ENV, organization["slug"])
    session = SessionLocal()
    try:
        _add_vehicle(session, organization, "provider-vehicle-1", "UNIT-1")
        _add_vehicle(session, organization, "provider-vehicle-2", "UNIT-2")
        _add_vehicle(session, organization, "provider-vehicle-3", "UNIT-3")
        session.commit()
        connector = V1FallbackConnector()
        result = certify_assignment_signal_schema(session, certification_date=DAY, connector=connector)
    finally:
        session.close()

    location = result["resources"]["vehicle_location"]
    assert location["available"] is True
    assert location["non_empty_sample_found"] is True
    assert location["source_endpoint_version"] == "v1_latest"
    assert location["vehicles_examined"] == 3
    assert location["v1_fallback_examined"] == 2
    assert "$.vehicle_location.located_at" in location["observed_schema_paths"]
    assert "$.vehicle_location.lat" in location["observed_schema_paths"]
    assert "$.vehicle_location.lon" in location["observed_schema_paths"]
    v1_calls = [call for call in connector.calls if call[0].startswith("/v1/vehicle_locations/")]
    assert len(v1_calls) == 2
    assert all(call[1] == {"date": "2026-09-10"} for call in v1_calls)
    assert all("provider-vehicle-3" not in call[0] for call in v1_calls)
    serialized = repr(result)
    for forbidden in ("provider-vehicle-1", "provider-vehicle-2", "UNIT-1", "UNIT-2", "49.89", "-97.13"):
        assert forbidden not in serialized


def test_machine_endpoint_is_hmac_bodyless_and_privacy_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET)
    expected = {
        "status": "certification_completed",
        "provider": "motive",
        "operation": "assignment_signal_schema_certification",
        "certification_date": DAY.isoformat(),
        "resources": {
            "hours_of_service": {"available": True, "error_code": None, "provider_http_status": 200, "observed_schema_paths": {"$": ["object"]}},
            "vehicle_location": {
                "available": False,
                "error_code": "permission_denied",
                "provider_http_status": 403,
                "observed_schema_paths": {},
                "vehicles_examined": 5,
                "lookback_days": 7,
                "non_empty_sample_found": False,
                "source_endpoint_version": "none",
                "v1_fallback_examined": 5,
            },
        },
        "schema_values_returned": False,
        "raw_provider_payloads_returned": False,
        "driver_identity_values_returned": False,
        "vehicle_identity_values_returned": False,
        "coordinates_returned": False,
        "secrets_exposed": False,
    }
    monkeypatch.setattr(internal_motive, "certify_assignment_signal_schema", lambda *_args, **_kwargs: expected)
    client = TestClient(app)

    assert client.post(f"{PATH}?date={DAY.isoformat()}").status_code == 401

    body = b'{"unsafe":true}'
    rejected = client.post(
        f"{PATH}?date={DAY.isoformat()}",
        content=body,
        headers=_signed_headers(body=body),
    )
    assert rejected.status_code == 400

    response = client.post(f"{PATH}?date={DAY.isoformat()}", headers=_signed_headers())
    assert response.status_code == 200
    assert response.json() == expected


def test_workflow_is_manual_only_and_does_not_receive_provider_key() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = (repo_root / ".github" / "workflows" / "motive-assignment-signal-certification.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert PATH in workflow
    assert "POLARIS_PRODUCTION_API_URL" in workflow
    assert "POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET" in workflow
    assert "MOTIVE_API_KEY" not in workflow
    assert "/v1/hours_of_service" not in workflow
    assert "/v3/vehicle_locations" not in workflow
    assert "/v1/vehicle_locations" not in workflow
    assert 'payload.get(key) is not False' in workflow
