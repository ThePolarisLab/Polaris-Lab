from __future__ import annotations

from datetime import date
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import internal_motive
from app.database.database import SessionLocal
from app.main import app
from app.motive.maintenance_signal_certification import certify_maintenance_signal_schema
from app.security.job_auth import sign_job_request
from tests.auth_helpers import seed_principal

PATH = "/api/v1/internal/motive/maintenance-signal-certification"
SECRET_ENV = "POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET"
ORG_ENV = "POLARIS_MOTIVE_UTILIZATION_SCHEDULED_ORGANIZATION_SLUG"
SECRET = "motive-maintenance-signal-certification-test-secret"
DAY = date(2026, 9, 12)


class FakeConnector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str]] = []

    def _request_json(self, endpoint: str, *, params: dict, operation: str):
        self.calls.append((endpoint, params, operation))
        if endpoint == "/v1/fault_codes":
            return {
                "fault_codes": [
                    {
                        "fault_code": {
                            "id": 99,
                            "code": "SPN-SECRET",
                            "status": "open",
                            "dtc_severity": "critical",
                            "first_observed_at": "2026-09-12T01:00:00Z",
                            "vehicle": {"id": 5, "number": "M2209", "vin": "VIN-SECRET"},
                        }
                    }
                ],
                "pagination": {"total": 1},
            }
        if endpoint == "/v2/inspection_reports":
            return {
                "inspection_reports": [
                    {
                        "inspection_report": {
                            "id": 17,
                            "date": "2026-09-12",
                            "status": "open",
                            "vehicle": {"id": 5, "number": "M2209", "vin": "VIN-SECRET"},
                            "inspected_parts": [
                                {
                                    "name": "Brakes",
                                    "status": "open",
                                    "defects": [
                                        {
                                            "id": 3,
                                            "title": "Synthetic secret defect",
                                            "severity": "major",
                                            "notes": "SECRET NOTE",
                                        }
                                    ],
                                }
                            ],
                            "driver_signature_url": "https://secret.example/signature",
                        }
                    }
                ],
                "pagination": {"total": 1},
            }
        raise AssertionError(f"unexpected provider call: {endpoint}")


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


def test_schema_certification_returns_structure_only(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, _headers = seed_principal("owner")
    monkeypatch.setenv(ORG_ENV, organization["slug"])
    session = SessionLocal()
    try:
        connector = FakeConnector()
        result = certify_maintenance_signal_schema(session, certification_date=DAY, connector=connector)
    finally:
        session.close()

    assert result["status"] == "certification_completed"
    assert result["lookback_days"] == 7
    assert result["schema_values_returned"] is False
    assert result["raw_provider_payloads_returned"] is False
    assert result["vehicle_identity_values_returned"] is False
    assert result["fault_code_values_returned"] is False
    assert result["inspection_defect_values_returned"] is False
    assert result["inspection_notes_returned"] is False
    assert result["signature_urls_returned"] is False
    assert result["secrets_exposed"] is False
    assert result["maintenance_readiness_changed"] is False
    assert result["dispatch_readiness_changed"] is False

    faults = result["resources"]["fault_codes"]
    inspections = result["resources"]["inspection_reports"]
    assert faults["available"] is True
    assert inspections["available"] is True
    assert faults["non_empty_sample_found"] is True
    assert inspections["non_empty_sample_found"] is True
    assert "$.fault_codes[].fault_code.status" in faults["observed_schema_paths"]
    assert "$.fault_codes[].fault_code.dtc_severity" in faults["observed_schema_paths"]
    assert "$.inspection_reports[].inspection_report.inspected_parts[].defects[].severity" in inspections["observed_schema_paths"]

    assert connector.calls == [
        (
            "/v1/fault_codes",
            {"start_date": "2026-09-06", "end_date": "2026-09-12", "per_page": 5, "page_no": 1},
            "maintenance_signal_fault_code_certification",
        ),
        (
            "/v2/inspection_reports",
            {"updated_after": "2026-09-06", "entity_type": "vehicle", "per_page": 5, "page_no": 1},
            "maintenance_signal_inspection_report_certification",
        ),
    ]

    rendered = repr(result)
    for forbidden in (
        "SPN-SECRET",
        "M2209",
        "VIN-SECRET",
        "Synthetic secret defect",
        "SECRET NOTE",
        "https://secret.example/signature",
    ):
        assert forbidden not in rendered


def test_machine_endpoint_is_hmac_bodyless_and_privacy_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET)
    expected = {
        "status": "certification_completed",
        "provider": "motive",
        "operation": "maintenance_signal_schema_certification",
        "certification_date": DAY.isoformat(),
        "lookback_days": 7,
        "resources": {
            "fault_codes": {
                "available": True,
                "error_code": None,
                "provider_http_status": 200,
                "observed_schema_paths": {"$": ["object"]},
                "non_empty_sample_found": False,
            },
            "inspection_reports": {
                "available": True,
                "error_code": None,
                "provider_http_status": 200,
                "observed_schema_paths": {"$": ["object"]},
                "non_empty_sample_found": False,
            },
        },
        "schema_values_returned": False,
        "raw_provider_payloads_returned": False,
        "vehicle_identity_values_returned": False,
        "fault_code_values_returned": False,
        "inspection_defect_values_returned": False,
        "inspection_notes_returned": False,
        "signature_urls_returned": False,
        "secrets_exposed": False,
        "maintenance_readiness_changed": False,
        "dispatch_readiness_changed": False,
    }
    monkeypatch.setattr(internal_motive, "certify_maintenance_signal_schema", lambda *_args, **_kwargs: expected)
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
    workflow = (repo_root / ".github" / "workflows" / "motive-maintenance-signal-certification.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert PATH in workflow
    assert "POLARIS_PRODUCTION_API_URL" in workflow
    assert "POLARIS_MOTIVE_UTILIZATION_CRON_TRIGGER_SECRET" in workflow
    assert "MOTIVE_API_KEY" not in workflow
    assert "/v1/fault_codes" not in workflow
    assert "/v2/inspection_reports" not in workflow
    assert 'payload.get(key) is not False' in workflow
