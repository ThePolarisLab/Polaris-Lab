from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.dashboard import service
from app.dashboard.models import DashboardItem
from app.database.database import Base
from app.models.motive import MotiveSyncCheckpoint, MotiveSyncHistory
from app.organizations.models import Organization


ORG_A = "org-a"
ORG_B = "org-b"
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


def _status_payload(
    *,
    operational_status: str,
    production_status: str = "success",
    checkpoint_status: str = "success",
    production_enabled: bool = False,
    scheduler_enabled: bool = False,
    scheduler_claim_status: str = "not_claimed",
) -> dict:
    return {
        "operational_status": operational_status,
        "production": {
            "status": production_status,
            "error_code": "secret-like-error-should-not-leak",
            "run_id": "run-id-should-not-leak",
            "provider_vehicle_id": "vehicle-id-should-not-leak",
        },
        "checkpoint": {
            "status": checkpoint_status,
            "unrestricted": "checkpoint-secret-should-not-leak",
        },
        "scheduler": {
            "claim_status": scheduler_claim_status,
            "unrestricted": "scheduler-secret-should-not-leak",
        },
        "configuration": {
            "production_ingestion_enabled": production_enabled,
            "production_scheduler_enabled": scheduler_enabled,
            "controlled_validation_window_enabled": False,
        },
        "secrets_exposed": False,
    }


def _stub_operational_status(monkeypatch, payload: dict):
    calls: list[str] = []

    def fake(_db, organization_id: str):
        calls.append(organization_id)
        return payload

    monkeypatch.setattr(service, "vehicle_utilization_operational_status", fake)
    return calls


def test_healthy_status_adds_no_system_health_item(monkeypatch):
    calls = _stub_operational_status(monkeypatch, _status_payload(operational_status="healthy"))

    item = service._motive_utilization_health(object(), ORG_A)

    assert item is None
    assert calls == [ORG_A]


def test_degraded_status_adds_one_sanitized_high_item(monkeypatch):
    payload = _status_payload(
        operational_status="degraded",
        production_status="failed",
        checkpoint_status="failed",
        scheduler_claim_status="claimed",
    )
    _stub_operational_status(monkeypatch, payload)

    item = service._motive_utilization_health(object(), ORG_A)

    assert item == DashboardItem(
        "Motive vehicle utilization needs review",
        "Latest production vehicle-utilization run did not complete successfully; review Motive operational status.",
        "HIGH",
        "Motive Vehicle Utilization",
    )
    serialized = " ".join((item.title, item.detail, item.source, item.entity_id or ""))
    for forbidden in (
        "secret-like-error",
        "run-id-should-not-leak",
        "vehicle-id-should-not-leak",
        "checkpoint-secret",
        "scheduler-secret",
    ):
        assert forbidden not in serialized


def test_degraded_status_uses_checkpoint_then_mismatch_detail(monkeypatch):
    _stub_operational_status(
        monkeypatch,
        _status_payload(
            operational_status="degraded",
            production_status="success",
            checkpoint_status="failed",
        ),
    )
    checkpoint_item = service._motive_utilization_health(object(), ORG_A)
    assert checkpoint_item.detail == (
        "Production vehicle-utilization checkpoint is not successful; review Motive operational status."
    )

    _stub_operational_status(
        monkeypatch,
        _status_payload(
            operational_status="degraded",
            production_status="success",
            checkpoint_status="success",
        ),
    )
    mismatch_item = service._motive_utilization_health(object(), ORG_A)
    assert mismatch_item.detail == (
        "Production utilization history and checkpoint are inconsistent; review Motive operational status."
    )


def test_not_started_enabled_adds_one_medium_item(monkeypatch):
    _stub_operational_status(
        monkeypatch,
        _status_payload(
            operational_status="not_started",
            production_status="not_started",
            checkpoint_status="not_started",
            production_enabled=True,
        ),
    )

    item = service._motive_utilization_health(object(), ORG_A)

    assert item == DashboardItem(
        "Motive vehicle utilization has no production history",
        "Production vehicle-utilization capability is enabled, but no production history is available.",
        "MEDIUM",
        "Motive Vehicle Utilization",
    )


def test_not_started_disabled_and_scheduler_claim_alone_adds_no_item(monkeypatch):
    _stub_operational_status(
        monkeypatch,
        _status_payload(
            operational_status="not_started",
            production_status="not_started",
            checkpoint_status="not_started",
            production_enabled=False,
            scheduler_enabled=False,
            scheduler_claim_status="claimed",
        ),
    )

    assert service._motive_utilization_health(object(), ORG_A) is None


def test_read_exception_keeps_dashboard_health_available_and_sanitized(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("database-password-should-not-leak")

    monkeypatch.setattr(service, "vehicle_utilization_operational_status", fail)

    item = service._motive_utilization_health(object(), ORG_A)

    assert item == DashboardItem(
        "Motive utilization health could not be read",
        "Motive vehicle-utilization operational health is unavailable; review Motive operational status.",
        "HIGH",
        "Motive Vehicle Utilization",
    )
    assert "database-password" not in item.detail


def test_ace_and_motive_health_items_can_coexist(monkeypatch):
    ace_item = DashboardItem(
        "ACE daily feed needs review",
        "No recent successful feed.",
        "HIGH",
        "ACE Daily Feed",
        "#executive/ace",
    )
    monkeypatch.setattr(service, "_ace_feed_attention", lambda *_args: ace_item)
    _stub_operational_status(
        monkeypatch,
        _status_payload(
            operational_status="degraded",
            production_status="failed",
            checkpoint_status="success",
        ),
    )

    items = service._system_health(object(), ORG_A)

    assert items[0] == ace_item
    assert items[1].source == "Motive Vehicle Utilization"
    assert items[1].severity == "HIGH"


class _EmptyQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return []

    def count(self):
        return 0


class _DashboardDB:
    def query(self, *_args, **_kwargs):
        return _EmptyQuery()


def test_motive_health_does_not_change_business_status_plan_attention_or_watch(monkeypatch):
    _stub_operational_status(
        monkeypatch,
        _status_payload(
            operational_status="degraded",
            production_status="failed",
            checkpoint_status="failed",
        ),
    )
    monkeypatch.setattr(
        service,
        "analyze_q2_compliance_risk",
        lambda *_args: SimpleNamespace(
            risk=SimpleNamespace(value="LOW"),
            evidence_count=0,
            recommendation="No connected risk evidence was found.",
            mission_id="mission.q2_compliance",
        ),
    )

    dashboard = service.build_executive_dashboard(_DashboardDB(), organization_id=ORG_A)

    assert dashboard.business_status == "RUNNING NORMALLY"
    assert dashboard.needs_attention == ()
    assert dashboard.watch_items == ()
    assert all(item.source != "Motive Vehicle Utilization" for item in dashboard.todays_plan)
    assert dashboard.daily_brief.needs_attention == ()
    assert dashboard.daily_brief.todays_priority == ()
    motive_items = [
        item
        for item in dashboard.daily_brief.system_health
        if item.source == "Motive Vehicle Utilization"
    ]
    assert len(motive_items) == 1
    assert motive_items[0].severity == "HIGH"


@pytest.fixture()
def motive_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Organization.__table__, MotiveSyncHistory.__table__, MotiveSyncCheckpoint.__table__],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db, engine
    finally:
        db.close()
        engine.dispose()


def _history(
    *,
    organization_id: str,
    status: str = "success",
    started_at: datetime = NOW,
    completed_through: str = "2026-08-21",
) -> MotiveSyncHistory:
    return MotiveSyncHistory(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_resource="vehicle_utilization",
        mode="production_recent_window_ingestion",
        status=status,
        run_id=f"run-{organization_id}-{started_at.timestamp()}",
        started_at=started_at,
        completed_at=started_at,
        records_read=68,
        records_written=68,
        error_code=None if status == "success" else "secret-like-error-code",
        checkpoint_before={},
        checkpoint_after={"completed_through": completed_through} if status == "success" else {},
        resource_counts={
            "horizon_days": 7,
            "request_timezone": "America/Chicago",
            "unit_request_mode": "imperial",
            "fuel_unit": "gallons",
            "provider_vehicle_id": "must-not-leak",
        },
    )


def _checkpoint(
    *,
    organization_id: str,
    status: str = "success",
    completed_through: str = "2026-08-21",
) -> MotiveSyncCheckpoint:
    return MotiveSyncCheckpoint(
        organization_id=organization_id,
        organization_slug=organization_id,
        provider="motive",
        provider_resource="vehicle_utilization",
        checkpoint_status=status,
        last_successful_sync_at=NOW,
        last_successful_position={
            "completed_through": completed_through,
            "request_timezone": "America/Chicago",
            "unit_request_mode": "imperial",
            "fuel_unit": "gallons",
            "secret_like_value": "must-not-leak",
        },
    )


def test_cross_tenant_rows_cannot_influence_daily_brief_motive_health(motive_session):
    db, _engine = motive_session
    db.add_all(
        [
            Organization(id=ORG_A, slug=ORG_A, display_name=ORG_A),
            Organization(id=ORG_B, slug=ORG_B, display_name=ORG_B),
            _history(organization_id=ORG_A, status="success", started_at=NOW),
            _checkpoint(organization_id=ORG_A, status="success"),
            _history(
                organization_id=ORG_B,
                status="failed",
                started_at=datetime(2026, 8, 22, 13, 0, tzinfo=timezone.utc),
            ),
            _checkpoint(organization_id=ORG_B, status="failed"),
        ]
    )
    db.commit()

    assert service._motive_utilization_health(db, ORG_A) is None
    other_tenant_item = service._motive_utilization_health(db, ORG_B)
    assert other_tenant_item is not None
    assert other_tenant_item.severity == "HIGH"


def test_daily_brief_motive_health_read_performs_selects_only(motive_session):
    db, engine = motive_session
    db.add_all(
        [
            Organization(id=ORG_A, slug=ORG_A, display_name=ORG_A),
            _history(organization_id=ORG_A),
            _checkpoint(organization_id=ORG_A),
        ]
    )
    db.commit()

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.strip())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        before_new = len(db.new)
        before_dirty = len(db.dirty)
        before_deleted = len(db.deleted)

        item = service._motive_utilization_health(db, ORG_A)

        assert item is None
        assert len(db.new) == before_new
        assert len(db.dirty) == before_dirty
        assert len(db.deleted) == before_deleted
        assert statements
        assert all(statement.upper().startswith("SELECT") for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
