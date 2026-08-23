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
from app.models.motive import MotiveSyncHistory
from app.models.motive_kpi_snapshot import MotiveVehicleUtilizationKpiSnapshot
from app.motive import vehicle_utilization_kpi_history as history
from app.organizations.models import Organization
from tests.auth_helpers import seed_principal


ORG_A = "org-history-a"
ORG_B = "org-history-b"
AS_OF = date(2026, 8, 22)
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def history_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            MotiveSyncHistory.__table__,
            MotiveVehicleUtilizationKpiSnapshot.__table__,
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


def _history(db: Session, organization_id: str, *, suffix: str = "1") -> MotiveSyncHistory:
    row = MotiveSyncHistory(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_resource="vehicle_utilization",
        mode="production_recent_window_ingestion",
        status="success",
        run_id=f"history-run-{organization_id}-{suffix}",
        started_at=NOW,
        completed_at=NOW,
        records_read=0,
        records_written=0,
        checkpoint_before={},
        checkpoint_after={"completed_through": AS_OF.isoformat()},
        resource_counts={
            "horizon_days": 7,
            "request_timezone": "America/Chicago",
            "unit_request_mode": "imperial",
            "fuel_unit": "gallons",
            "x_metric_units": False,
            "selected_vehicle_count": 2,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _snapshot(
    db: Session,
    *,
    organization_id: str,
    source_history_id: int,
    window_end: date,
    value: Decimal | None,
    status: str = "available_observed",
    coverage: Decimal = Decimal("57.14"),
    metric_valid: int = 8,
    expected: int = 14,
    fleet_representative: bool = False,
    kpi: str = history.KPI_NAME,
) -> MotiveVehicleUtilizationKpiSnapshot:
    row = MotiveVehicleUtilizationKpiSnapshot(
        organization_id=organization_id,
        organization_slug=organization_id,
        kpi=kpi,
        kpi_version=1,
        status=status,
        window_start=window_end - timedelta(days=6),
        window_end=window_end,
        request_timezone="America/Chicago",
        value_percent=value,
        selected_vehicle_count=2,
        expected_requested_vehicle_days=expected,
        provider_rollup_vehicle_days=10,
        metric_valid_vehicle_days=metric_valid,
        missing_requested_vehicle_days=4,
        provider_rollup_coverage_percent=Decimal("71.43"),
        utilization_metric_coverage_percent=coverage,
        fleet_representative=fleet_representative,
        fuel_unit="gallons",
        unit_request_mode="imperial",
        source_history_id=source_history_id,
        computed_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def test_history_uses_inclusive_calendar_horizon_orders_points_and_preserves_gaps(history_session):
    db, _engine = history_session
    _organization(db, ORG_A)
    source = _history(db, ORG_A)
    _snapshot(db, organization_id=ORG_A, source_history_id=source.id, window_end=date(2026, 7, 23), value=Decimal("11"))
    _snapshot(db, organization_id=ORG_A, source_history_id=source.id, window_end=date(2026, 7, 24), value=Decimal("22"))
    _snapshot(db, organization_id=ORG_A, source_history_id=source.id, window_end=date(2026, 8, 1), value=Decimal("33"))
    _snapshot(db, organization_id=ORG_A, source_history_id=source.id, window_end=date(2026, 8, 22), value=Decimal("44"))
    _snapshot(db, organization_id=ORG_A, source_history_id=source.id, window_end=date(2026, 8, 23), value=Decimal("55"))

    result = history.vehicle_utilization_kpi_history(db, ORG_A, days=30, end_date=AS_OF)

    assert result["requested_history_days"] == 30
    assert result["history_start"] == "2026-07-24"
    assert result["history_end"] == "2026-08-22"
    assert result["snapshot_count"] == 3
    assert [point["window_end"] for point in result["points"]] == [
        "2026-07-24",
        "2026-08-01",
        "2026-08-22",
    ]
    assert result["points"][0]["value_percent"] == 22.0
    assert result["points"][1]["value_percent"] == 33.0
    assert result["points"][2]["value_percent"] == 44.0


def test_history_is_tenant_scoped_and_preserves_zero_and_unavailable(history_session):
    db, _engine = history_session
    _organization(db, ORG_A)
    _organization(db, ORG_B)
    source_a = _history(db, ORG_A)
    source_b = _history(db, ORG_B)
    _snapshot(
        db,
        organization_id=ORG_A,
        source_history_id=source_a.id,
        window_end=date(2026, 8, 20),
        value=Decimal("0"),
        coverage=Decimal("100"),
        metric_valid=14,
        expected=14,
        fleet_representative=True,
    )
    _snapshot(
        db,
        organization_id=ORG_A,
        source_history_id=source_a.id,
        window_end=date(2026, 8, 21),
        value=None,
        status="unavailable",
        coverage=Decimal("0"),
        metric_valid=0,
    )
    _snapshot(
        db,
        organization_id=ORG_B,
        source_history_id=source_b.id,
        window_end=date(2026, 8, 21),
        value=Decimal("99"),
    )

    result = history.vehicle_utilization_kpi_history(db, ORG_A, days=7, end_date=AS_OF)

    assert result["snapshot_count"] == 2
    assert result["points"][0]["value_percent"] == 0.0
    assert result["points"][0]["fleet_representative"] is True
    assert result["points"][1]["status"] == "unavailable"
    assert result["points"][1]["value_percent"] is None
    assert all(point["value_percent"] != 99.0 for point in result["points"])


def test_history_exposes_aggregate_fields_only(history_session):
    db, _engine = history_session
    _organization(db, ORG_A)
    source = _history(db, ORG_A)
    _snapshot(db, organization_id=ORG_A, source_history_id=source.id, window_end=AS_OF, value=Decimal("46.74"))

    result = history.vehicle_utilization_kpi_history(db, ORG_A, days=1, end_date=AS_OF)
    serialized = json.dumps(result, sort_keys=True)

    assert result["secrets_exposed"] is False
    assert "history-run-org-history-a" not in serialized
    for forbidden in (
        "source_history_id",
        "run_id",
        "provider_vehicle_id",
        "vin",
        "license_plate",
        "raw_payload",
        "api_key",
        "bearer_token",
    ):
        assert forbidden not in serialized


def test_history_read_executes_selects_only(history_session):
    db, engine = history_session
    _organization(db, ORG_A)
    source = _history(db, ORG_A)
    _snapshot(db, organization_id=ORG_A, source_history_id=source.id, window_end=AS_OF, value=Decimal("46.74"))
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.strip())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        before_new = len(db.new)
        before_dirty = len(db.dirty)
        before_deleted = len(db.deleted)

        result = history.vehicle_utilization_kpi_history(db, ORG_A, days=30, end_date=AS_OF)

        assert result["snapshot_count"] == 1
        assert len(db.new) == before_new
        assert len(db.dirty) == before_dirty
        assert len(db.deleted) == before_deleted
        assert statements
        assert all(statement.upper().startswith("SELECT") for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_history_service_rejects_out_of_bounds_days(history_session):
    db, _engine = history_session
    with pytest.raises(history.MotiveVehicleUtilizationKpiHistoryError):
        history.vehicle_utilization_kpi_history(db, ORG_A, days=0, end_date=AS_OF)
    with pytest.raises(history.MotiveVehicleUtilizationKpiHistoryError):
        history.vehicle_utilization_kpi_history(db, ORG_A, days=91, end_date=AS_OF)


def test_history_endpoint_accepts_connector_read_enforces_bounds_and_makes_no_provider_call(monkeypatch):
    organization, _identity, headers = seed_principal("viewer")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            MotiveSyncHistory.__table__,
            MotiveVehicleUtilizationKpiSnapshot.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        db.add(
            Organization(
                id=organization["id"],
                slug=organization["slug"],
                display_name=organization["display_name"],
            )
        )
        db.commit()
        source = _history(db, organization["id"])
        _snapshot(
            db,
            organization_id=organization["id"],
            source_history_id=source.id,
            window_end=date(2026, 8, 21),
            value=Decimal("46.74"),
        )

        def forbidden_provider_call(*_args, **_kwargs):
            raise AssertionError("read-only KPI history endpoint must not call Motive")

        monkeypatch.setattr(MotiveConnector, "_request_json", forbidden_provider_call)
        monkeypatch.setattr(history, "latest_completed_day", lambda: AS_OF)

        def override_db():
            yield db

        app.dependency_overrides[kpi_api._db] = override_db
        client = TestClient(app)

        response = client.get(
            "/api/v1/motive/fleet/vehicle-utilization-kpi/history?days=7",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["requested_history_days"] == 7
        assert body["snapshot_count"] == 1
        assert body["points"][0]["value_percent"] == 46.74
        assert body["secrets_exposed"] is False

        assert client.get(
            "/api/v1/motive/fleet/vehicle-utilization-kpi/history?days=0",
            headers=headers,
        ).status_code == 422
        assert client.get(
            "/api/v1/motive/fleet/vehicle-utilization-kpi/history?days=91",
            headers=headers,
        ).status_code == 422
    finally:
        app.dependency_overrides.pop(kpi_api._db, None)
        db.close()
        engine.dispose()
