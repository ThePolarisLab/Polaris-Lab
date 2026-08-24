from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import motive_vehicle_utilization_kpi as kpi_api
from app.connectors.motive import MotiveConnector
from app.database.database import Base
from app.main import app
from app.models.motive import (
    MotiveSyncCheckpoint,
    MotiveSyncHistory,
    MotiveVehicleRecord,
    MotiveVehicleUtilizationRecord,
)
from app.motive.vehicle_driving_fuel_burn_rate_kpi import vehicle_driving_fuel_burn_rate_kpi
from app.motive.vehicle_utilization_production_ingestion import (
    PRODUCTION_FUEL_UNIT,
    PRODUCTION_HORIZON_DAYS,
    PRODUCTION_TIME_ZONE,
    PRODUCTION_UNIT_REQUEST_MODE,
)
from app.organizations.models import Organization
from tests.auth_helpers import seed_principal


ORG_A = "org-driving-burn-kpi-a"
ORG_B = "org-driving-burn-kpi-b"
WINDOW_END = date(2026, 8, 22)
WINDOW_START = WINDOW_END - timedelta(days=PRODUCTION_HORIZON_DAYS - 1)
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def kpi_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            MotiveVehicleRecord.__table__,
            MotiveVehicleUtilizationRecord.__table__,
            MotiveSyncHistory.__table__,
            MotiveSyncCheckpoint.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db, engine
    finally:
        db.close()
        engine.dispose()


def _organization(db: Session, organization_id: str) -> None:
    db.add(Organization(id=organization_id, slug=organization_id, display_name=organization_id))
    db.commit()


def _seed_operational_context(
    db: Session,
    *,
    organization_id: str,
    selected_vehicle_count: int,
    status: str = "success",
    started_at: datetime = NOW,
    window_end: date = WINDOW_END,
) -> None:
    completed_through = window_end.isoformat()
    db.add(
        MotiveSyncHistory(
            organization_id=organization_id,
            organization_slug=organization_id,
            provider="motive",
            provider_resource="vehicle_utilization",
            mode="production_recent_window_ingestion",
            status=status,
            run_id=f"run-{organization_id}-{started_at.isoformat()}-{status}",
            started_at=started_at,
            completed_at=started_at,
            records_read=0,
            records_written=0,
            checkpoint_before={},
            checkpoint_after={"completed_through": completed_through} if status == "success" else {},
            resource_counts={
                "horizon_days": PRODUCTION_HORIZON_DAYS,
                "request_timezone": PRODUCTION_TIME_ZONE,
                "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
                "fuel_unit": PRODUCTION_FUEL_UNIT,
                "selected_vehicle_count": selected_vehicle_count,
            },
        )
    )
    if status == "success":
        db.add(
            MotiveSyncCheckpoint(
                organization_id=organization_id,
                organization_slug=organization_id,
                provider="motive",
                provider_resource="vehicle_utilization",
                checkpoint_status="success",
                last_successful_sync_at=started_at,
                last_successful_position={
                    "completed_through": completed_through,
                    "request_timezone": PRODUCTION_TIME_ZONE,
                    "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
                    "fuel_unit": PRODUCTION_FUEL_UNIT,
                },
            )
        )
    db.commit()


def _vehicles(db: Session, organization_id: str, count: int) -> list[MotiveVehicleRecord]:
    rows = [
        MotiveVehicleRecord(
            organization_id=organization_id,
            organization_slug=organization_id,
            provider="motive",
            provider_vehicle_id=f"provider-{organization_id}-{index}",
            unit_number=f"unit-{organization_id}-{index}",
        )
        for index in range(1, count + 1)
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _rollup(
    db: Session,
    *,
    organization_id: str,
    vehicle: MotiveVehicleRecord,
    day: date,
    driving_time: Decimal | None,
    driving_fuel: Decimal | None,
    metric_units: bool | None = False,
    end_day: date | None = None,
) -> MotiveVehicleUtilizationRecord:
    row = MotiveVehicleUtilizationRecord(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_vehicle_id=vehicle.provider_vehicle_id,
        motive_vehicle_id=vehicle.id,
        request_window_start=day,
        request_window_end=end_day or day,
        driving_time=driving_time,
        driving_fuel=driving_fuel,
        metric_units=metric_units,
    )
    db.add(row)
    db.commit()
    return row


def _seed_healthy_org(db: Session, organization_id: str, vehicle_count: int) -> list[MotiveVehicleRecord]:
    _organization(db, organization_id)
    _seed_operational_context(db, organization_id=organization_id, selected_vehicle_count=vehicle_count)
    return _vehicles(db, organization_id, vehicle_count)


def test_ratio_of_sums_converts_seconds_to_driving_hours_and_reports_coverage(kpi_session):
    db, _engine = kpi_session
    vehicles = _seed_healthy_org(db, ORG_A, 2)

    # Row burn rates are 2.0 and 1.333... gal/driving-hour. Their simple mean
    # would be about 1.67, but the required ratio of sums is 3 gal / 2 h = 1.50.
    _rollup(db, organization_id=ORG_A, vehicle=vehicles[0], day=WINDOW_START, driving_time=Decimal("1800"), driving_fuel=Decimal("1"))
    _rollup(db, organization_id=ORG_A, vehicle=vehicles[1], day=WINDOW_START, driving_time=Decimal("5400"), driving_fuel=Decimal("2"))
    _rollup(db, organization_id=ORG_A, vehicle=vehicles[0], day=WINDOW_START + timedelta(days=1), driving_time=Decimal("0"), driving_fuel=Decimal("0"))
    _rollup(db, organization_id=ORG_A, vehicle=vehicles[1], day=WINDOW_START + timedelta(days=1), driving_time=None, driving_fuel=Decimal("1"))
    _rollup(db, organization_id=ORG_A, vehicle=vehicles[0], day=WINDOW_START + timedelta(days=2), driving_time=Decimal("3600"), driving_fuel=Decimal("9"), metric_units=True)
    _rollup(db, organization_id=ORG_A, vehicle=vehicles[1], day=WINDOW_START + timedelta(days=2), driving_time=Decimal("3600"), driving_fuel=Decimal("9"), end_day=WINDOW_START + timedelta(days=3))
    _rollup(db, organization_id=ORG_A, vehicle=vehicles[0], day=WINDOW_START - timedelta(days=1), driving_time=Decimal("3600"), driving_fuel=Decimal("9"))

    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)

    assert result == {
        "status": "available_observed",
        "kpi": "observed_7_day_driving_fuel_burn_rate",
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "request_timezone": "America/Chicago",
        "value_gallons_per_driving_hour": 1.5,
        "selected_vehicle_count": 2,
        "expected_requested_vehicle_days": 14,
        "provider_rollup_vehicle_days": 5,
        "metric_valid_vehicle_days": 2,
        "missing_requested_vehicle_days": 9,
        "provider_rollup_coverage_percent": 35.71,
        "driving_fuel_burn_rate_metric_coverage_percent": 14.29,
        "fleet_representative": False,
        "driving_time_unit": "seconds",
        "fuel_unit": "gallons",
        "rate_unit": "gallons_per_driving_hour",
        "unit_request_mode": "imperial",
        "secrets_exposed": False,
    }


def test_positive_driving_time_with_zero_fuel_is_real_zero_rate(kpi_session):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=Decimal("3600"), driving_fuel=Decimal("0"))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["status"] == "available_observed"
    assert result["value_gallons_per_driving_hour"] == 0.0
    assert result["metric_valid_vehicle_days"] == 1


def test_zero_time_zero_fuel_has_no_burn_rate_denominator(kpi_session):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=Decimal("0"), driving_fuel=Decimal("0"))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["status"] == "unavailable"
    assert result["value_gallons_per_driving_hour"] is None
    assert result["provider_rollup_vehicle_days"] == 1
    assert result["metric_valid_vehicle_days"] == 0
    assert result["driving_fuel_burn_rate_metric_coverage_percent"] == 0.0


def test_zero_driving_time_with_positive_fuel_fails_closed(kpi_session):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=Decimal("0"), driving_fuel=Decimal("1"))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["status"] == "unavailable"
    assert result["value_gallons_per_driving_hour"] is None
    assert result["provider_rollup_vehicle_days"] == 1
    assert result["driving_fuel_burn_rate_metric_coverage_percent"] is None


@pytest.mark.parametrize(
    ("driving_time", "driving_fuel"),
    [(Decimal("-1"), Decimal("1")), (Decimal("3600"), Decimal("-1"))],
)
def test_negative_driving_metric_fails_closed(kpi_session, driving_time, driving_fuel):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=driving_time, driving_fuel=driving_fuel)
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["status"] == "unavailable"
    assert result["driving_fuel_burn_rate_metric_coverage_percent"] is None


def test_null_driving_metric_is_incomplete_not_zero(kpi_session):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=None, driving_fuel=Decimal("1"))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["status"] == "unavailable"
    assert result["value_gallons_per_driving_hour"] is None
    assert result["metric_valid_vehicle_days"] == 0


def test_full_metric_coverage_is_fleet_representative(kpi_session):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    for offset in range(PRODUCTION_HORIZON_DAYS):
        _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START + timedelta(days=offset), driving_time=Decimal("3600"), driving_fuel=Decimal("8.25"))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["value_gallons_per_driving_hour"] == 8.25
    assert result["provider_rollup_coverage_percent"] == 100.0
    assert result["driving_fuel_burn_rate_metric_coverage_percent"] == 100.0
    assert result["fleet_representative"] is True


def test_historical_population_change_fails_closed(kpi_session):
    db, _engine = kpi_session
    _organization(db, ORG_A)
    _seed_operational_context(db, organization_id=ORG_A, selected_vehicle_count=2)
    _vehicles(db, ORG_A, 1)
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["status"] == "unavailable"
    assert result["selected_vehicle_count"] == 2
    assert result["expected_requested_vehicle_days"] is None


def test_latest_failed_production_state_makes_kpi_unavailable(kpi_session):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=Decimal("3600"), driving_fuel=Decimal("8"))
    _seed_operational_context(db, organization_id=ORG_A, selected_vehicle_count=1, status="failed", started_at=NOW + timedelta(hours=1))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["status"] == "unavailable"
    assert result["value_gallons_per_driving_hour"] is None


def test_cross_tenant_rows_cannot_influence_result(kpi_session):
    db, _engine = kpi_session
    vehicle_a = _seed_healthy_org(db, ORG_A, 1)[0]
    vehicle_b = _seed_healthy_org(db, ORG_B, 1)[0]
    for offset in range(PRODUCTION_HORIZON_DAYS):
        day = WINDOW_START + timedelta(days=offset)
        _rollup(db, organization_id=ORG_A, vehicle=vehicle_a, day=day, driving_time=Decimal("3600"), driving_fuel=Decimal("8"))
        _rollup(db, organization_id=ORG_B, vehicle=vehicle_b, day=day, driving_time=Decimal("3600"), driving_fuel=Decimal("20"))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    assert result["value_gallons_per_driving_hour"] == 8.0
    assert result["metric_valid_vehicle_days"] == 7


def test_response_is_sanitized_and_does_not_expose_raw_totals(kpi_session):
    db, _engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=Decimal("3600"), driving_fuel=Decimal("8"))
    result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
    serialized = json.dumps(result, sort_keys=True)
    assert "provider-org-driving-burn-kpi-a-1" not in serialized
    assert "run-org-driving-burn-kpi-a" not in serialized
    for forbidden_key in (
        "provider_vehicle_id",
        "motive_vehicle_id",
        "vin",
        "license_plate",
        "unit_number",
        "run_id",
        "source_history_id",
        "raw_provider_payload",
        "api_key",
        "token",
        "observed_driving_seconds",
        "observed_driving_fuel_gallons",
        "distance",
        "engine_hours",
    ):
        assert forbidden_key not in result
    assert result["secrets_exposed"] is False


def test_kpi_read_executes_selects_only(kpi_session):
    db, engine = kpi_session
    vehicle = _seed_healthy_org(db, ORG_A, 1)[0]
    _rollup(db, organization_id=ORG_A, vehicle=vehicle, day=WINDOW_START, driving_time=Decimal("3600"), driving_fuel=Decimal("8"))
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.strip())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        before_new = len(db.new)
        before_dirty = len(db.dirty)
        before_deleted = len(db.deleted)
        result = vehicle_driving_fuel_burn_rate_kpi(db, ORG_A)
        assert result["status"] == "available_observed"
        assert len(db.new) == before_new
        assert len(db.dirty) == before_dirty
        assert len(db.deleted) == before_deleted
        assert statements
        assert all(statement.upper().startswith("SELECT") for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_endpoint_accepts_connector_read_and_makes_no_provider_call(monkeypatch):
    organization, _identity, headers = seed_principal("viewer")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            MotiveVehicleRecord.__table__,
            MotiveVehicleUtilizationRecord.__table__,
            MotiveSyncHistory.__table__,
            MotiveSyncCheckpoint.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        db.add(Organization(id=organization["id"], slug=organization["slug"], display_name=organization["display_name"]))
        db.commit()
        _seed_operational_context(db, organization_id=organization["id"], selected_vehicle_count=1)
        vehicle = _vehicles(db, organization["id"], 1)[0]
        for offset in range(PRODUCTION_HORIZON_DAYS):
            _rollup(db, organization_id=organization["id"], vehicle=vehicle, day=WINDOW_START + timedelta(days=offset), driving_time=Decimal("7200"), driving_fuel=Decimal("18"))

        def forbidden_provider_call(*_args, **_kwargs):
            raise AssertionError("read-only driving-fuel-burn-rate endpoint must not call Motive")

        monkeypatch.setattr(MotiveConnector, "_request_json", forbidden_provider_call)

        def override_db():
            yield db

        app.dependency_overrides[kpi_api._db] = override_db
        client = TestClient(app)
        response = client.get("/api/v1/motive/fleet/vehicle-driving-fuel-burn-rate-kpi", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "available_observed"
        assert body["kpi"] == "observed_7_day_driving_fuel_burn_rate"
        assert body["value_gallons_per_driving_hour"] == 9.0
        assert body["fleet_representative"] is True
        assert body["driving_time_unit"] == "seconds"
        assert body["fuel_unit"] == "gallons"
        assert body["rate_unit"] == "gallons_per_driving_hour"
        assert body["unit_request_mode"] == "imperial"
        assert body["secrets_exposed"] is False
    finally:
        app.dependency_overrides.pop(kpi_api._db, None)
        db.close()
        engine.dispose()
