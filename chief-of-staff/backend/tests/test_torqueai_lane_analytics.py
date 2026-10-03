from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop
from tests.auth_helpers import seed_principal


def _seed(org_id: str, load: str, customer: str, miles: str | None, charge: str | None, currency: str | None, pickup_city: str, pickup_province: str, delivery_province: str) -> None:
    now = datetime.now(timezone.utc)
    row = TorqueAIDispatch(
        organization_id=org_id, provider_load_number=load, provider_order_number=f"ORD-{load}",
        status="delivered", ship_date_text="2026-06-15", customer_name=customer,
        loaded_miles=Decimal(miles) if miles is not None else None, source_fingerprint=load.zfill(64)[-64:],
        first_observed_at=now, last_changed_at=now,
    )
    session = SessionLocal()
    try:
        session.add(row); session.flush()
        session.add(TorqueAIDispatchOperational(
            organization_id=org_id, dispatch_id=row.id, currency=currency,
            total_charge=Decimal(charge) if charge is not None else None,
            source_fingerprint=("a"+load).zfill(64)[-64:], first_observed_at=now, last_changed_at=now,
        ))
        for idx, job, city, province, country in (
            (0, "Pick Up", pickup_city, pickup_province, "Canada"),
            (1, "Drop Off", "Fort Worth", delivery_province, "USA"),
        ):
            session.add(TorqueAIDispatchStop(
                organization_id=org_id, dispatch_id=row.id, stop_index=idx, job=job, city=city,
                province=province, country=country, source_fingerprint=(str(idx)+load).zfill(64)[-64:],
                first_observed_at=now, last_changed_at=now,
            ))
        session.commit()
    finally:
        session.close()


def test_lane_analytics_matches_pickup_and_delivery_on_same_dispatch_and_calculates_weighted_rpm() -> None:
    org, _identity, headers = seed_principal("viewer")
    other, _other_identity, _other_headers = seed_principal("viewer")
    _seed(org["id"], "1", "Canada Packers", "1000", "3000", "CAD", "Winnipeg", "MB", "TX")
    _seed(org["id"], "2", "Canada Packers", "2000", "8000", "CAD", "Winnipeg", "MB", "TX")
    _seed(org["id"], "3", "Canada Packers", "1500", "9000", "CAD", "Brandon", "MB", "TX")
    _seed(org["id"], "4", "Other", "1000", "9000", "CAD", "Winnipeg", "MB", "TX")
    _seed(other["id"], "9", "Canada Packers", "1", "999999", "CAD", "Winnipeg", "MB", "TX")

    response = TestClient(app).get(
        "/api/v1/torqueai/analytics/lane?from=2026-01-01&to=2026-10-03&customer=canada%20packers&pickup_city=winnipeg&pickup_province=mb&delivery_province=tx&delivery_country=usa",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["load_count"] == 2
    cad = payload["currency_metrics"]["CAD"]
    assert cad["total_revenue"] == 11000
    assert cad["total_loaded_miles"] == 3000
    assert cad["average_revenue_per_load"] == 5500
    assert cad["weighted_revenue_per_loaded_mile"] == 11000 / 3000
    assert payload["provider_called"] is False
    assert payload["tenant_scope_validated"] is True
    assert payload["secrets_exposed"] is False


def test_lane_analytics_keeps_currencies_separate_and_reports_missing_data() -> None:
    org, _identity, headers = seed_principal("owner")
    _seed(org["id"], "11", "Canada Packers", None, "3000", "CAD", "Winnipeg", "MB", "TX")
    _seed(org["id"], "12", "Canada Packers", "1000", None, "CAD", "Winnipeg", "MB", "TX")
    _seed(org["id"], "13", "Canada Packers", "1000", "2000", "USD", "Winnipeg", "MB", "TX")
    response = TestClient(app).get("/api/v1/torqueai/analytics/lane?from=2026-01-01&to=2026-10-03&customer=Canada%20Packers&pickup_province=MB&delivery_province=TX", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["load_count"] == 3
    assert payload["missing_loaded_miles_count"] == 1
    assert payload["missing_revenue_or_currency_count"] == 1
    assert set(payload["currency_metrics"]) == {"CAD", "USD"}


def test_lane_analytics_rejects_more_than_one_year() -> None:
    _org, _identity, headers = seed_principal("owner")
    response = TestClient(app).get("/api/v1/torqueai/analytics/lane?from=2025-01-01&to=2026-10-03", headers=headers)
    assert response.status_code == 422
