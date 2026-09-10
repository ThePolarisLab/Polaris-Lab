from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.connectors.torqueai import TorqueAIDispatchPage
from app.connectors.torqueai_operational_ingestion import (
    TorqueAIDispatchIngestionError,
    ingest_torqueai_dispatches,
)
from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational
from tests.auth_helpers import seed_principal

DAY = date(2026, 9, 10)


class FakeConnector:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.calls = 0

    def fetch_dispatches(self, *, date_from, date_to, page, limit):
        self.calls += 1
        assert page == 1
        assert limit == 100
        return TorqueAIDispatchPage(
            data=tuple(self.records),
            total_count=len(self.records),
            page=1,
            items_per_page=100,
            date_from=date_from,
            date_to=date_to,
        )


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
        "stops": [{"synthetic": "one"}, {"synthetic": "two"}],
        "billing": {"synthetic": True},
    }
    item.update(overrides)
    return item


def test_certified_operational_fields_persist_without_extra_provider_calls() -> None:
    organization, _identity, _headers = seed_principal("owner")
    connector = FakeConnector([dispatch()])
    session = SessionLocal()
    try:
        result = ingest_torqueai_dispatches(
            session,
            organization_id=organization["id"],
            organization_slug=organization["slug"],
            date_from=DAY,
            date_to=DAY,
            connector=connector,
        )
        assert result["rows_inserted"] == 1
        assert connector.calls == 1

        base = session.query(TorqueAIDispatch).filter_by(organization_id=organization["id"]).one()
        enrichment = session.query(TorqueAIDispatchOperational).filter_by(
            organization_id=organization["id"], dispatch_id=base.id
        ).one()
        assert enrichment.currency == "CAD"
        assert enrichment.total_charge == Decimal("3200.2500")
        assert enrichment.stop_count == 2
        assert len(enrichment.source_fingerprint) == 64
    finally:
        session.close()


def test_missing_optional_operational_fields_persist_as_null() -> None:
    organization, _identity, _headers = seed_principal("owner")
    connector = FakeConnector([dispatch(currency=None, totalCharge=None, stops=None)])
    session = SessionLocal()
    try:
        ingest_torqueai_dispatches(
            session,
            organization_id=organization["id"],
            organization_slug=organization["slug"],
            date_from=DAY,
            date_to=DAY,
            connector=connector,
        )
        enrichment = session.query(TorqueAIDispatchOperational).filter_by(
            organization_id=organization["id"]
        ).one()
        assert enrichment.currency is None
        assert enrichment.total_charge is None
        assert enrichment.stop_count is None
    finally:
        session.close()


@pytest.mark.parametrize(
    "override",
    [
        {"currency": 123},
        {"totalCharge": "3200.25"},
        {"stops": {"not": "an array"}},
    ],
)
def test_invalid_certified_operational_types_fail_before_dispatch_persistence(override: dict) -> None:
    organization, _identity, _headers = seed_principal("owner")
    connector = FakeConnector([dispatch(**override)])
    session = SessionLocal()
    try:
        with pytest.raises(TorqueAIDispatchIngestionError, match="provider_contract_error"):
            ingest_torqueai_dispatches(
                session,
                organization_id=organization["id"],
                organization_slug=organization["slug"],
                date_from=DAY,
                date_to=DAY,
                connector=connector,
            )
        assert session.query(TorqueAIDispatch).filter_by(organization_id=organization["id"]).count() == 0
        assert session.query(TorqueAIDispatchOperational).filter_by(organization_id=organization["id"]).count() == 0
    finally:
        session.close()


def test_operational_only_change_updates_fingerprint_and_sync_classification() -> None:
    organization, _identity, _headers = seed_principal("owner")
    connector = FakeConnector([dispatch()])
    session = SessionLocal()
    try:
        first = ingest_torqueai_dispatches(
            session,
            organization_id=organization["id"],
            organization_slug=organization["slug"],
            date_from=DAY,
            date_to=DAY,
            connector=connector,
        )
        enrichment = session.query(TorqueAIDispatchOperational).filter_by(
            organization_id=organization["id"]
        ).one()
        first_fingerprint = enrichment.source_fingerprint
        first_changed = enrichment.last_changed_at

        connector.records = [dispatch(totalCharge=3300.75)]
        second = ingest_torqueai_dispatches(
            session,
            organization_id=organization["id"],
            organization_slug=organization["slug"],
            date_from=DAY,
            date_to=DAY,
            connector=connector,
        )
        session.expire_all()
        enrichment = session.query(TorqueAIDispatchOperational).filter_by(
            organization_id=organization["id"]
        ).one()

        assert first["rows_inserted"] == 1
        assert second["rows_updated"] == 1
        assert second["rows_unchanged"] == 0
        assert enrichment.total_charge == Decimal("3300.7500")
        assert enrichment.source_fingerprint != first_fingerprint
        assert enrichment.last_changed_at >= first_changed
        assert session.query(TorqueAIDispatch).filter_by(organization_id=organization["id"]).count() == 1
        assert session.query(TorqueAIDispatchOperational).filter_by(organization_id=organization["id"]).count() == 1
        assert connector.calls == 2
    finally:
        session.close()


def test_durable_read_serializes_enrichment_and_filters_case_insensitively() -> None:
    organization, _identity, headers = seed_principal("owner")
    other_organization, _other_identity, _other_headers = seed_principal("owner")
    observed = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        row = TorqueAIDispatch(
            organization_id=organization["id"],
            provider_load_number="9001",
            provider_order_number="ORD-9001",
            status="Dispatched",
            order_date_text="2026-09-09",
            ship_date_text="2026-09-10",
            delivery_date_text="2026-09-11",
            customer_name="Canada Packers",
            dispatcher_name="Alice",
            driver_name="Driver One",
            carrier_name="MOR Logistics",
            truck_number="2218",
            trailer_number="R-34",
            loaded_miles=Decimal("450.5000"),
            source_fingerprint="a" * 64,
            first_observed_at=observed,
            last_changed_at=observed,
        )
        other = TorqueAIDispatch(
            organization_id=other_organization["id"],
            provider_load_number="9999",
            provider_order_number="ORD-OTHER",
            status="Dispatched",
            order_date_text="2026-09-09",
            ship_date_text="2026-09-10",
            delivery_date_text="2026-09-11",
            customer_name="Other Tenant",
            dispatcher_name="Alice",
            driver_name="Driver One",
            carrier_name="MOR Logistics",
            truck_number="2218",
            trailer_number="R-34",
            loaded_miles=Decimal("1"),
            source_fingerprint="b" * 64,
            first_observed_at=observed,
            last_changed_at=observed,
        )
        session.add_all([row, other])
        session.flush()
        session.add_all([
            TorqueAIDispatchOperational(
                organization_id=organization["id"], dispatch_id=row.id,
                currency="CAD", total_charge=Decimal("3200.2500"), stop_count=2,
                source_fingerprint="c" * 64, first_observed_at=observed, last_changed_at=observed,
            ),
            TorqueAIDispatchOperational(
                organization_id=other_organization["id"], dispatch_id=other.id,
                currency="CAD", total_charge=Decimal("9999"), stop_count=3,
                source_fingerprint="d" * 64, first_observed_at=observed, last_changed_at=observed,
            ),
        ])
        session.commit()
    finally:
        session.close()

    response = TestClient(app).get(
        "/api/v1/torqueai/dispatches?from=2026-09-10&to=2026-09-10&driver=driver%20one&truck=2218&carrier=mor%20logistics&trailer=r-34&currency=cad",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    item = payload["data"][0]
    assert item["load_number"] == "9001"
    assert item["currency"] == "CAD"
    assert item["total_charge"] == 3200.25
    assert item["stop_count"] == 2
    assert "ORD-OTHER" not in response.text
    assert payload["provider_called"] is False
    assert payload["tenant_scope_validated"] is True
