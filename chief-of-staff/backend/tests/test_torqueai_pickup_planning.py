from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.database.database import SessionLocal
from app.main import app
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop
from tests.auth_helpers import seed_principal


NOW = datetime.now(timezone.utc)
TARGET_DATE = "2026-09-11"


def _add_dispatch(
    *,
    organization_id: str,
    load_number: str,
    pickup_province: str,
    pickup_city: str,
    pickup_job: str = "Pick Up",
    pickup_date: str = TARGET_DATE,
    driver: str | None = "Driver One",
    truck: str | None = "2218",
    trailer: str | None = "R-34",
) -> None:
    session = SessionLocal()
    try:
        row = TorqueAIDispatch(
            organization_id=organization_id,
            provider_load_number=load_number,
            provider_order_number=f"ORD-{load_number}",
            status="Dispatched",
            order_date_text="2026-09-10",
            ship_date_text=pickup_date,
            delivery_date_text="2026-09-12",
            customer_name="Planning Customer",
            dispatcher_name="Dispatcher One",
            driver_name=driver,
            carrier_name="MOR Logistics",
            truck_number=truck,
            trailer_number=trailer,
            loaded_miles=Decimal("1500.0"),
            source_fingerprint=(load_number * 64)[:64],
            first_observed_at=NOW,
            last_changed_at=NOW,
        )
        session.add(row)
        session.flush()
        session.add(
            TorqueAIDispatchOperational(
                organization_id=organization_id,
                dispatch_id=row.id,
                currency="USD",
                total_charge=Decimal("6000.0"),
                stop_count=2,
                source_fingerprint=("e" + load_number * 64)[:64],
                first_observed_at=NOW,
                last_changed_at=NOW,
            )
        )
        session.add_all(
            [
                TorqueAIDispatchStop(
                    organization_id=organization_id,
                    dispatch_id=row.id,
                    stop_index=0,
                    sequence=Decimal("1"),
                    stop_no="1",
                    job=pickup_job,
                    name="Origin Facility",
                    address="100 Origin Rd",
                    city=pickup_city,
                    province=pickup_province,
                    country="Canada",
                    zip_code="R3C 0A1",
                    scheduled_is_window=True,
                    scheduled_pickup_date_text=pickup_date,
                    scheduled_pickup_time_text="09:00",
                    scheduled_pickup_time2_text="10:00",
                    commodity="Food",
                    temperature_text="-10",
                    temperature_unit="C",
                    weight=Decimal("42000"),
                    weight_unit="lb",
                    source_fingerprint=("p" + load_number * 64)[:64],
                    first_observed_at=NOW,
                    last_changed_at=NOW,
                ),
                TorqueAIDispatchStop(
                    organization_id=organization_id,
                    dispatch_id=row.id,
                    stop_index=1,
                    sequence=Decimal("2"),
                    stop_no="2",
                    job="Drop Off",
                    name="Destination Facility",
                    address="200 Destination Rd",
                    city="Laredo",
                    province="TX",
                    country="USA",
                    scheduled_pickup_date_text="2026-09-12",
                    scheduled_pickup_time_text="14:00",
                    source_fingerprint=("d" + load_number * 64)[:64],
                    first_observed_at=NOW,
                    last_changed_at=NOW,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()


def test_pickup_plan_returns_only_true_same_stop_manitoba_pickups() -> None:
    organization, _identity, headers = seed_principal("owner")
    _add_dispatch(
        organization_id=organization["id"],
        load_number="8101",
        pickup_province="MB",
        pickup_city="Winnipeg",
    )
    _add_dispatch(
        organization_id=organization["id"],
        load_number="8102",
        pickup_province="TX",
        pickup_city="Laredo",
    )

    session = SessionLocal()
    try:
        second = session.query(TorqueAIDispatch).filter_by(
            organization_id=organization["id"], provider_load_number="8102"
        ).one()
        session.add(
            TorqueAIDispatchStop(
                organization_id=organization["id"],
                dispatch_id=second.id,
                stop_index=2,
                sequence=Decimal("3"),
                stop_no="3",
                job="Drop Off",
                city="Winnipeg",
                province="MB",
                country="Canada",
                scheduled_pickup_date_text=TARGET_DATE,
                source_fingerprint="x" * 64,
                first_observed_at=NOW,
                last_changed_at=NOW,
            )
        )
        session.commit()
    finally:
        session.close()

    response = TestClient(app).get(
        f"/api/v1/torqueai/planning/pickups?date={TARGET_DATE}&province=mb",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_scope"] == "pickup_read_only"
    assert payload["summary"]["pickup_load_count"] == 1
    assert payload["loads"][0]["load_number"] == "8101"
    assert payload["loads"][0]["pickup_stops"][0]["job"] == "Pick Up"
    assert payload["loads"][0]["pickup_stops"][0]["province"] == "MB"
    assert payload["loads"][0]["drop_off_stops"][0]["job"] == "Drop Off"
    assert "8102" not in response.text
    assert payload["provider_called"] is False
    assert payload["autonomous_assignment_performed"] is False


def test_pickup_plan_surfaces_assignment_gaps_and_is_tenant_scoped() -> None:
    organization, _identity, headers = seed_principal("owner")
    other, _other_identity, _other_headers = seed_principal("owner")
    _add_dispatch(
        organization_id=organization["id"],
        load_number="8201",
        pickup_province="MB",
        pickup_city="Brandon",
        driver=None,
        truck=None,
        trailer=None,
    )
    _add_dispatch(
        organization_id=other["id"],
        load_number="8999",
        pickup_province="MB",
        pickup_city="Brandon",
    )

    response = TestClient(app).get(
        f"/api/v1/torqueai/planning/pickups?date={TARGET_DATE}&province=MB&city=brandon",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "pickup_load_count": 1,
        "attention_required_count": 1,
        "missing_driver_count": 1,
        "missing_truck_count": 1,
    }
    assert payload["loads"][0]["load_number"] == "8201"
    assert payload["loads"][0]["attention_flags"] == [
        "missing_driver",
        "missing_truck",
        "missing_trailer",
    ]
    assert "8999" not in response.text
    assert payload["tenant_scope_validated"] is True
    assert payload["secrets_exposed"] is False
