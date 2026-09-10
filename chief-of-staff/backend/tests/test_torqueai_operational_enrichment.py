from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.connectors.torqueai import TorqueAIDispatchPage
from app.connectors.torqueai_operational_ingestion import TorqueAIDispatchIngestionError, ingest_torqueai_dispatches
from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop
from tests.auth_helpers import seed_principal

DAY = date(2026, 9, 10)


class FakeConnector:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.calls = 0

    def fetch_dispatches(self, *, date_from, date_to, page, limit):
        self.calls += 1
        return TorqueAIDispatchPage(data=tuple(self.records), total_count=len(self.records), page=page, items_per_page=limit, date_from=date_from, date_to=date_to)


def stop(**overrides) -> dict:
    item = {
        "sequence": 1,
        "stopNo": "1",
        "job": "SYNTHETIC_ROLE",
        "name": "Synthetic Facility",
        "address": "1 Test Road",
        "city": "Winnipeg",
        "province": "MB",
        "country": "Canada",
        "zipCode": "R3C 0A1",
        "latitude": 49.8951,
        "longitude": -97.1384,
        "commodity": "Synthetic Food",
        "notes": "Synthetic note",
        "driverName": "Driver One",
        "coDriverName": "Driver Two",
        "carrierName": "MOR Logistics",
        "truckNumber": "2218",
        "trailerNumber": "R-34",
        "scheduled": {"isWindow": True, "pickupDate": "2026-09-10", "pickupDate2": "2026-09-10", "pickupTime": "08:00", "pickupTime2": "10:00"},
        "temperature": -10,
        "temperatureUnit": "C",
        "weight": 42000,
        "weightUnit": "lb",
    }
    item.update(overrides)
    return item


def dispatch(**overrides) -> dict:
    item = {
        "loadNumber": 1053,
        "orderNumber": "ORD-1053",
        "status": "dispatched",
        "orderDate": "2026-09-09",
        "shipDate": "2026-09-10",
        "deliveryDate": "2026-09-11",
        "customerName": "Canada Packers",
        "dispatcherName": "Alice",
        "driverName": "Driver One",
        "carrierName": "MOR Logistics",
        "truckNumber": "2218",
        "trailerNumber": "R-34",
        "loadedMiles": 450.5,
        "currency": "CAD",
        "totalCharge": 3200.25,
        "stops": [stop(), stop(sequence=2, stopNo="2", city="Laredo", province="TX", country="USA", temperature="-10")],
        "billing": {"currency": "CAD", "rate": 3000, "subTotal": 3000, "taxAmount": 200.25, "total": 3200.25},
    }
    item.update(overrides)
    return item


def test_certified_operational_fields_and_stops_persist_without_extra_provider_calls() -> None:
    organization, _identity, _headers = seed_principal("owner")
    connector = FakeConnector([dispatch()])
    session = SessionLocal()
    try:
        result = ingest_torqueai_dispatches(session, organization_id=organization["id"], organization_slug=organization["slug"], date_from=DAY, date_to=DAY, connector=connector)
        assert result["rows_inserted"] == 1
        assert connector.calls == 1
        base = session.query(TorqueAIDispatch).filter_by(organization_id=organization["id"]).one()
        enrichment = session.query(TorqueAIDispatchOperational).filter_by(organization_id=organization["id"], dispatch_id=base.id).one()
        stops = session.query(TorqueAIDispatchStop).filter_by(organization_id=organization["id"], dispatch_id=base.id).order_by(TorqueAIDispatchStop.stop_index).all()
        assert enrichment.currency == "CAD"
        assert enrichment.total_charge == Decimal("3200.2500")
        assert enrichment.billing_total == Decimal("3200.2500")
        assert enrichment.stop_count == 2
        assert len(stops) == 2
        assert stops[0].city == "Winnipeg"
        assert stops[0].province == "MB"
        assert stops[0].commodity == "Synthetic Food"
        assert stops[0].weight == Decimal("42000.0000")
        assert stops[0].temperature_text == "-10"
        assert stops[1].temperature_text == "-10"
    finally:
        session.close()


def test_missing_optional_operational_fields_persist_as_null() -> None:
    organization, _identity, _headers = seed_principal("owner")
    connector = FakeConnector([dispatch(currency=None, totalCharge=None, stops=None, billing=None)])
    session = SessionLocal()
    try:
        ingest_torqueai_dispatches(session, organization_id=organization["id"], organization_slug=organization["slug"], date_from=DAY, date_to=DAY, connector=connector)
        enrichment = session.query(TorqueAIDispatchOperational).filter_by(organization_id=organization["id"]).one()
        assert enrichment.currency is None
        assert enrichment.total_charge is None
        assert enrichment.stop_count is None
        assert session.query(TorqueAIDispatchStop).filter_by(organization_id=organization["id"]).count() == 0
    finally:
        session.close()


@pytest.mark.parametrize("override", [{"currency": 123}, {"totalCharge": "3200.25"}, {"stops": {"not": "an array"}}, {"billing": "bad"}])
def test_invalid_certified_operational_types_fail_closed(override: dict) -> None:
    organization, _identity, _headers = seed_principal("owner")
    session = SessionLocal()
    try:
        with pytest.raises(TorqueAIDispatchIngestionError) as exc_info:
            ingest_torqueai_dispatches(session, organization_id=organization["id"], organization_slug=organization["slug"], date_from=DAY, date_to=DAY, connector=FakeConnector([dispatch(**override)]))
        assert exc_info.value.code == "provider_contract_error"
        assert session.query(TorqueAIDispatch).filter_by(organization_id=organization["id"]).count() == 0
    finally:
        session.close()


def test_stop_only_change_updates_operational_fingerprint_and_replaces_stops() -> None:
    organization, _identity, _headers = seed_principal("owner")
    connector = FakeConnector([dispatch()])
    session = SessionLocal()
    try:
        first = ingest_torqueai_dispatches(session, organization_id=organization["id"], organization_slug=organization["slug"], date_from=DAY, date_to=DAY, connector=connector)
        original = session.query(TorqueAIDispatchOperational).filter_by(organization_id=organization["id"]).one().source_fingerprint
        connector.records = [dispatch(stops=[stop(city="Brandon", province="MB")])]
        second = ingest_torqueai_dispatches(session, organization_id=organization["id"], organization_slug=organization["slug"], date_from=DAY, date_to=DAY, connector=connector)
        session.expire_all()
        enrichment = session.query(TorqueAIDispatchOperational).filter_by(organization_id=organization["id"]).one()
        stops = session.query(TorqueAIDispatchStop).filter_by(organization_id=organization["id"]).all()
        assert first["rows_inserted"] == 1
        assert second["rows_updated"] == 1
        assert enrichment.source_fingerprint != original
        assert enrichment.stop_count == 1
        assert len(stops) == 1 and stops[0].city == "Brandon"
        assert connector.calls == 2
    finally:
        session.close()


def test_durable_stop_filters_are_case_insensitive_and_tenant_scoped() -> None:
    organization, _identity, headers = seed_principal("owner")
    other, _other_identity, _other_headers = seed_principal("owner")
    observed = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        def add_dispatch(org: dict, number: str, city: str) -> None:
            row = TorqueAIDispatch(
                organization_id=org["id"], provider_load_number=number, provider_order_number=f"ORD-{number}", status="Dispatched",
                order_date_text="2026-09-09", ship_date_text="2026-09-10", delivery_date_text="2026-09-11", customer_name="Customer",
                dispatcher_name="Alice", driver_name="Driver One", carrier_name="MOR Logistics", truck_number="2218", trailer_number="R-34",
                loaded_miles=Decimal("450.5"), source_fingerprint=("a" if org is organization else "b") * 64, first_observed_at=observed, last_changed_at=observed,
            )
            session.add(row); session.flush()
            session.add(TorqueAIDispatchOperational(organization_id=org["id"], dispatch_id=row.id, currency="CAD", total_charge=Decimal("3200"), stop_count=1, source_fingerprint="c"*64, first_observed_at=observed, last_changed_at=observed))
            session.add(TorqueAIDispatchStop(organization_id=org["id"], dispatch_id=row.id, stop_index=0, sequence=Decimal("1"), job="SYNTHETIC_ROLE", city=city, province="MB", country="Canada", source_fingerprint="d"*64, first_observed_at=observed, last_changed_at=observed))
        add_dispatch(organization, "9001", "Winnipeg")
        add_dispatch(other, "9999", "Winnipeg")
        session.commit()
    finally:
        session.close()

    response = TestClient(app).get("/api/v1/torqueai/dispatches?from=2026-09-10&to=2026-09-10&stop_job=synthetic_role&stop_city=winnipeg&stop_province=mb&stop_country=canada", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["data"][0]["load_number"] == "9001"
    assert payload["data"][0]["stops"][0]["province"] == "MB"
    assert "9999" not in response.text
    assert payload["provider_called"] is False
    assert payload["tenant_scope_validated"] is True
