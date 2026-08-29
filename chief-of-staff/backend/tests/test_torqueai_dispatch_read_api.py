from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.connectors.torqueai import TorqueAIConnector
from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchSyncRun
from tests.auth_helpers import seed_principal


def _row(
    organization_id: str,
    load_number: str,
    order_number: str,
    *,
    ship_date: str,
    status: str = "delivered",
    customer: str = "Customer A",
    dispatcher: str = "Dispatcher A",
    changed_at: datetime | None = None,
) -> TorqueAIDispatch:
    observed = changed_at or datetime.now(timezone.utc)
    return TorqueAIDispatch(
        organization_id=organization_id,
        provider_load_number=load_number,
        provider_order_number=order_number,
        status=status,
        order_date_text="2026-08-25",
        ship_date_text=ship_date,
        delivery_date_text="2026-08-28",
        customer_name=customer,
        dispatcher_name=dispatcher,
        driver_name="Driver A",
        carrier_name="Carrier A",
        truck_number="T-100",
        trailer_number="R-200",
        loaded_miles=Decimal("612.5000"),
        source_fingerprint=(load_number.zfill(64))[-64:],
        first_observed_at=observed,
        last_changed_at=observed,
    )


def _get(headers: dict[str, str], query: str = ""):
    return TestClient(app).get(f"/api/v1/torqueai/dispatches{query}", headers=headers)


def test_durable_read_is_tenant_scoped_metadata_safe_and_never_calls_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    organization, _identity, headers = seed_principal("owner")
    other_organization, _other_identity, _other_headers = seed_principal("owner")
    provider_calls = 0

    def forbidden_provider_call(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("durable read must not call TorqueAI")

    monkeypatch.setattr(TorqueAIConnector, "fetch_dispatches", forbidden_provider_call)
    session = SessionLocal()
    try:
        session.add_all(
            [
                _row(organization["id"], "9001", "ORD-9001", ship_date="2026-08-27"),
                _row(organization["id"], "9002", "ORD-9002", ship_date="2026-08-28"),
                _row(other_organization["id"], "9999", "ORD-OTHER", ship_date="2026-08-27", customer="Other Tenant"),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = _get(headers, "?from=2026-08-27&to=2026-08-28&limit=100")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["provider"] == "torqueai"
    assert payload["source"] == "durable_database"
    assert payload["total_count"] == 2
    assert payload["rows_returned"] == 2
    assert payload["provider_called"] is False
    assert payload["tenant_scope_validated"] is True
    assert payload["secrets_exposed"] is False
    assert {item["load_number"] for item in payload["data"]} == {"9001", "9002"}
    assert "ORD-OTHER" not in response.text
    assert "Other Tenant" not in response.text
    assert "source_fingerprint" not in response.text
    assert "organization_id" not in response.text
    assert "billing" not in response.text
    assert "totalCharge" not in response.text
    assert "stops" not in response.text
    assert provider_calls == 0

    session = SessionLocal()
    try:
        assert session.query(TorqueAIDispatchSyncRun).count() == 0
        assert session.query(TorqueAIDispatch).filter(TorqueAIDispatch.organization_id == organization["id"]).count() == 2
    finally:
        session.close()


def test_durable_read_filters_case_insensitively_and_by_ship_date() -> None:
    organization, _identity, headers = seed_principal("owner")
    session = SessionLocal()
    try:
        session.add_all(
            [
                _row(organization["id"], "9101", "ORD-9101", ship_date="2026-08-27", status="Delivered", customer="Canada Packers", dispatcher="Alice"),
                _row(organization["id"], "9102", "ORD-9102", ship_date="2026-08-27T15:30:00Z", status="Delivered", customer="Other Customer", dispatcher="Alice"),
                _row(organization["id"], "9103", "ORD-9103", ship_date="2026-08-28", status="In Transit", customer="Canada Packers", dispatcher="Bob"),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = _get(
        headers,
        "?from=2026-08-27&to=2026-08-27&status=delivered&customer=canada%20packers&dispatcher=alice",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["rows_returned"] == 1
    assert payload["data"][0]["load_number"] == "9101"
    assert payload["request"]["status"] == "delivered"
    assert payload["request"]["customer"] == "canada packers"
    assert payload["request"]["dispatcher"] == "alice"


def test_durable_read_paginates_deterministically() -> None:
    organization, _identity, headers = seed_principal("owner")
    session = SessionLocal()
    try:
        session.add_all(
            [
                _row(organization["id"], "9201", "ORD-9201", ship_date="2026-08-27"),
                _row(organization["id"], "9202", "ORD-9202", ship_date="2026-08-27"),
                _row(organization["id"], "9203", "ORD-9203", ship_date="2026-08-27"),
            ]
        )
        session.commit()
    finally:
        session.close()

    first = _get(headers, "?page=1&limit=2")
    second = _get(headers, "?page=2&limit=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total_count"] == 3
    assert first.json()["rows_returned"] == 2
    assert first.json()["has_more"] is True
    assert second.json()["rows_returned"] == 1
    assert second.json()["has_more"] is False
    first_ids = {item["load_number"] for item in first.json()["data"]}
    second_ids = {item["load_number"] for item in second.json()["data"]}
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == {"9201", "9202", "9203"}


def test_viewer_with_connector_read_can_read_durable_dispatches() -> None:
    organization, _identity, headers = seed_principal("viewer")
    session = SessionLocal()
    try:
        session.add(_row(organization["id"], "9301", "ORD-9301", ship_date="2026-08-27"))
        session.commit()
    finally:
        session.close()

    response = _get(headers, "?from=2026-08-27&to=2026-08-27")
    assert response.status_code == 200
    assert response.json()["total_count"] == 1


def test_invalid_read_filters_fail_locally_without_provider_access(monkeypatch: pytest.MonkeyPatch) -> None:
    _organization, _identity, headers = seed_principal("owner")
    provider_calls = 0

    def forbidden_provider_call(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(TorqueAIConnector, "fetch_dispatches", forbidden_provider_call)

    missing_to = _get(headers, "?from=2026-08-27")
    reversed_window = _get(headers, "?from=2026-08-28&to=2026-08-27")
    over_bound = _get(headers, "?from=2026-07-28&to=2026-08-28")
    blank_status = _get(headers, "?status=%20%20")
    oversized_limit = _get(headers, "?limit=101")

    assert missing_to.status_code == 422
    assert reversed_window.status_code == 422
    assert over_bound.status_code == 422
    assert blank_status.status_code == 422
    assert oversized_limit.status_code == 422
    assert provider_calls == 0


def test_durable_read_module_has_no_provider_or_write_path() -> None:
    source = Path("app/api/torqueai.py").read_text(encoding="utf-8")
    assert "TorqueAIConnector" not in source
    assert "httpx" not in source
    assert ".commit(" not in source
    assert ".add(" not in source
    assert "session.delete" not in source
