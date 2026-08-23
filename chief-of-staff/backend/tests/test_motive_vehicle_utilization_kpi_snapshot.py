from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.database import Base
from app.models.motive import MotiveSyncHistory, MotiveVehicleRecord, MotiveVehicleUtilizationRecord
from app.models.motive_kpi_snapshot import MotiveVehicleUtilizationKpiSnapshot
from app.motive.vehicle_utilization_kpi_snapshot import (
    KPI_NAME,
    MotiveVehicleUtilizationKpiSnapshotError,
    calculate_vehicle_utilization_kpi_snapshot,
    load_vehicle_utilization_snapshot_rows,
    upsert_vehicle_utilization_kpi_snapshot,
)
from app.motive.vehicle_utilization_production_ingestion import (
    PRODUCTION_FUEL_UNIT,
    PRODUCTION_HORIZON_DAYS,
    PRODUCTION_TIME_ZONE,
    PRODUCTION_UNIT_REQUEST_MODE,
)
from app.organizations.models import Organization


ORG_A = "org-snapshot-a"
ORG_B = "org-snapshot-b"
WINDOW_END = date(2026, 8, 21)
WINDOW_START = WINDOW_END - timedelta(days=PRODUCTION_HORIZON_DAYS - 1)
NOW = datetime(2026, 8, 23, 3, 45, tzinfo=timezone.utc)


@pytest.fixture()
def snapshot_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            MotiveSyncHistory.__table__,
            MotiveVehicleRecord.__table__,
            MotiveVehicleUtilizationRecord.__table__,
            MotiveVehicleUtilizationKpiSnapshot.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        db.add_all(
            [
                Organization(id=ORG_A, slug=ORG_A, display_name=ORG_A),
                Organization(id=ORG_B, slug=ORG_B, display_name=ORG_B),
            ]
        )
        db.commit()
        yield db
    finally:
        db.close()
        engine.dispose()


def _row(
    *,
    organization_id: str = ORG_A,
    provider_vehicle_id: str,
    day: date,
    utilization: Decimal | None,
    metric_units: bool | None = False,
    end_day: date | None = None,
) -> MotiveVehicleUtilizationRecord:
    return MotiveVehicleUtilizationRecord(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_vehicle_id=provider_vehicle_id,
        motive_vehicle_id=None,
        request_window_start=day,
        request_window_end=end_day or day,
        utilization_percent=utilization,
        metric_units=metric_units,
    )


def _history(
    db: Session,
    *,
    organization_id: str = ORG_A,
    selected_vehicle_count: int = 2,
    window_end: date = WINDOW_END,
    status: str = "success",
    suffix: str = "1",
) -> MotiveSyncHistory:
    row = MotiveSyncHistory(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_resource="vehicle_utilization",
        mode="production_recent_window_ingestion",
        status=status,
        run_id=f"snapshot-history-{organization_id}-{suffix}",
        started_at=NOW,
        completed_at=NOW,
        records_read=0,
        records_written=0,
        checkpoint_before={},
        checkpoint_after={"completed_through": window_end.isoformat()},
        resource_counts={
            "horizon_days": PRODUCTION_HORIZON_DAYS,
            "request_timezone": PRODUCTION_TIME_ZONE,
            "unit_request_mode": PRODUCTION_UNIT_REQUEST_MODE.value,
            "fuel_unit": PRODUCTION_FUEL_UNIT,
            "x_metric_units": False,
            "selected_vehicle_count": selected_vehicle_count,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_calculator_preserves_partial_coverage_zero_and_exact_run_population():
    rows = [
        _row(provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("0")),
        _row(provider_vehicle_id="v2", day=WINDOW_START, utilization=Decimal("50")),
        _row(provider_vehicle_id="v1", day=WINDOW_START + timedelta(days=1), utilization=Decimal("100")),
        _row(provider_vehicle_id="v2", day=WINDOW_START + timedelta(days=1), utilization=None),
        _row(provider_vehicle_id="v1", day=WINDOW_START + timedelta(days=2), utilization=Decimal("80"), metric_units=True),
        _row(provider_vehicle_id="not-selected", day=WINDOW_START, utilization=Decimal("99")),
        _row(organization_id=ORG_B, provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("88")),
        _row(
            provider_vehicle_id="v2",
            day=WINDOW_START + timedelta(days=2),
            end_day=WINDOW_START + timedelta(days=3),
            utilization=Decimal("90"),
        ),
    ]

    result = calculate_vehicle_utilization_kpi_snapshot(
        organization_id=ORG_A,
        organization_slug=ORG_A,
        selected_provider_vehicle_ids=["v1", "v2"],
        window_end=WINDOW_END,
        rows=rows,
    )

    assert result.status == "available_observed"
    assert result.kpi == KPI_NAME
    assert result.value_percent == Decimal("50.00")
    assert result.selected_vehicle_count == 2
    assert result.expected_requested_vehicle_days == 14
    assert result.provider_rollup_vehicle_days == 5
    assert result.metric_valid_vehicle_days == 3
    assert result.missing_requested_vehicle_days == 9
    assert result.provider_rollup_coverage_percent == Decimal("35.71")
    assert result.utilization_metric_coverage_percent == Decimal("21.43")
    assert result.fleet_representative is False
    assert result.request_timezone == "America/Chicago"
    assert result.fuel_unit == "gallons"
    assert result.unit_request_mode == "imperial"


def test_calculator_unavailable_is_not_zero_and_does_not_require_current_fleet_rows():
    result = calculate_vehicle_utilization_kpi_snapshot(
        organization_id=ORG_A,
        organization_slug=ORG_A,
        selected_provider_vehicle_ids=["historical-provider-id"],
        window_end=WINDOW_END,
        rows=[
            _row(
                provider_vehicle_id="historical-provider-id",
                day=WINDOW_START,
                utilization=None,
            )
        ],
    )

    assert result.status == "unavailable"
    assert result.value_percent is None
    assert result.selected_vehicle_count == 1
    assert result.expected_requested_vehicle_days == 7
    assert result.provider_rollup_vehicle_days == 1
    assert result.metric_valid_vehicle_days == 0
    assert result.missing_requested_vehicle_days == 6
    assert result.utilization_metric_coverage_percent == Decimal("0.00")
    assert result.fleet_representative is False


def test_calculator_rejects_duplicate_selected_population_and_duplicate_vehicle_day():
    with pytest.raises(MotiveVehicleUtilizationKpiSnapshotError):
        calculate_vehicle_utilization_kpi_snapshot(
            organization_id=ORG_A,
            organization_slug=ORG_A,
            selected_provider_vehicle_ids=["v1", "v1"],
            window_end=WINDOW_END,
            rows=[],
        )

    duplicate = _row(provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("10"))
    with pytest.raises(MotiveVehicleUtilizationKpiSnapshotError):
        calculate_vehicle_utilization_kpi_snapshot(
            organization_id=ORG_A,
            organization_slug=ORG_A,
            selected_provider_vehicle_ids=["v1"],
            window_end=WINDOW_END,
            rows=[duplicate, duplicate],
        )


def test_loader_reads_only_exact_tenant_selection_without_current_vehicle_membership(snapshot_session):
    db = snapshot_session
    db.add_all(
        [
            _row(provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("10")),
            _row(provider_vehicle_id="not-selected", day=WINDOW_START, utilization=Decimal("20")),
            _row(organization_id=ORG_B, provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("30")),
            _row(provider_vehicle_id="v1", day=WINDOW_START - timedelta(days=1), utilization=Decimal("40")),
        ]
    )
    db.commit()

    rows = load_vehicle_utilization_snapshot_rows(
        db,
        organization_id=ORG_A,
        selected_provider_vehicle_ids=["v1"],
        window_end=WINDOW_END,
    )

    assert len(rows) == 1
    assert rows[0].organization_id == ORG_A
    assert rows[0].provider_vehicle_id == "v1"
    assert rows[0].request_window_start == WINDOW_START


def test_upsert_is_canonical_updates_same_window_and_does_not_commit(snapshot_session):
    db = snapshot_session
    first_history = _history(db, suffix="first")
    first = calculate_vehicle_utilization_kpi_snapshot(
        organization_id=ORG_A,
        organization_slug=ORG_A,
        selected_provider_vehicle_ids=["v1", "v2"],
        window_end=WINDOW_END,
        rows=[
            _row(provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("20")),
            _row(provider_vehicle_id="v2", day=WINDOW_START, utilization=Decimal("40")),
        ],
    )

    upsert_vehicle_utilization_kpi_snapshot(
        db,
        computation=first,
        source_history_id=first_history.id,
        computed_at=NOW,
    )
    assert db.query(MotiveVehicleUtilizationKpiSnapshot).count() == 1
    db.rollback()
    assert db.query(MotiveVehicleUtilizationKpiSnapshot).count() == 0

    first_row = upsert_vehicle_utilization_kpi_snapshot(
        db,
        computation=first,
        source_history_id=first_history.id,
        computed_at=NOW,
    )
    db.commit()
    first_id = first_row.id

    second_history = _history(db, suffix="second")
    second = calculate_vehicle_utilization_kpi_snapshot(
        organization_id=ORG_A,
        organization_slug=ORG_A,
        selected_provider_vehicle_ids=["v1", "v2"],
        window_end=WINDOW_END,
        rows=[
            _row(provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("60")),
            _row(provider_vehicle_id="v2", day=WINDOW_START, utilization=Decimal("80")),
        ],
    )
    updated = upsert_vehicle_utilization_kpi_snapshot(
        db,
        computation=second,
        source_history_id=second_history.id,
        computed_at=NOW + timedelta(minutes=5),
    )
    db.commit()

    assert db.query(MotiveVehicleUtilizationKpiSnapshot).count() == 1
    assert updated.id == first_id
    assert updated.value_percent == Decimal("70.0000")
    assert updated.source_history_id == second_history.id
    assert updated.selected_vehicle_count == 2


def test_same_window_is_tenant_isolated(snapshot_session):
    db = snapshot_session
    history_a = _history(db, organization_id=ORG_A, selected_vehicle_count=1, suffix="a")
    history_b = _history(db, organization_id=ORG_B, selected_vehicle_count=1, suffix="b")

    for organization_id, history in [(ORG_A, history_a), (ORG_B, history_b)]:
        computation = calculate_vehicle_utilization_kpi_snapshot(
            organization_id=organization_id,
            organization_slug=organization_id,
            selected_provider_vehicle_ids=["same-provider-id"],
            window_end=WINDOW_END,
            rows=[
                _row(
                    organization_id=organization_id,
                    provider_vehicle_id="same-provider-id",
                    day=WINDOW_START,
                    utilization=Decimal("25"),
                )
            ],
        )
        upsert_vehicle_utilization_kpi_snapshot(
            db,
            computation=computation,
            source_history_id=history.id,
        )
    db.commit()

    assert db.query(MotiveVehicleUtilizationKpiSnapshot).count() == 2
    assert {row.organization_id for row in db.query(MotiveVehicleUtilizationKpiSnapshot).all()} == {ORG_A, ORG_B}


def test_upsert_rejects_wrong_tenant_failed_or_semantically_mismatched_history(snapshot_session):
    db = snapshot_session
    computation = calculate_vehicle_utilization_kpi_snapshot(
        organization_id=ORG_A,
        organization_slug=ORG_A,
        selected_provider_vehicle_ids=["v1"],
        window_end=WINDOW_END,
        rows=[_row(provider_vehicle_id="v1", day=WINDOW_START, utilization=Decimal("10"))],
    )

    other_tenant = _history(db, organization_id=ORG_B, selected_vehicle_count=1, suffix="other")
    with pytest.raises(MotiveVehicleUtilizationKpiSnapshotError):
        upsert_vehicle_utilization_kpi_snapshot(db, computation=computation, source_history_id=other_tenant.id)

    failed = _history(db, selected_vehicle_count=1, status="failed", suffix="failed")
    with pytest.raises(MotiveVehicleUtilizationKpiSnapshotError):
        upsert_vehicle_utilization_kpi_snapshot(db, computation=computation, source_history_id=failed.id)

    wrong_count = _history(db, selected_vehicle_count=2, suffix="wrong-count")
    with pytest.raises(MotiveVehicleUtilizationKpiSnapshotError):
        upsert_vehicle_utilization_kpi_snapshot(db, computation=computation, source_history_id=wrong_count.id)

    assert db.query(MotiveVehicleUtilizationKpiSnapshot).count() == 0
