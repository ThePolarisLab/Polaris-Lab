"""Synthetic databases/providers only; never production credentials or traffic."""
from copy import deepcopy
from datetime import date, timedelta
import inspect

import pytest
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.connectors import torqueai_backfill_control as control_module
from app.connectors.torqueai_backfill_control import (
    BackfillControl, ControlError, _ledger_connection, fingerprint, rollback_eligible,
)
from app.models.torqueai_backfill import MANIFEST, WINDOW, ATTEMPT, IDENTITY
from app.models.torqueai import TorqueAIDispatch, TorqueAIDispatchOperational, TorqueAIDispatchStop
from test_torqueai_history_preview import TABLES, Provider, dispatch, seed, snapshot
from app.organizations.models import Organization

SHA = "a" * 40
DAY = date(2025, 6, 1)


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'control.db'}")
    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_connection, connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    for table in [*TABLES, MANIFEST, WINDOW, ATTEMPT, IDENTITY]:
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(insert(Organization.__table__), [
            {"id": "mor", "slug": "mor-logistics", "display_name": "MOR", "status": "active"},
            {"id": "other", "slug": "other", "display_name": "Other", "status": "active"}])
    monkeypatch.setenv("POLARIS_TORQUEAI_ORGANIZATION_SLUG", "mor-logistics")
    yield engine
    engine.dispose()


def plan(engine, windows=None):
    service = BackfillControl(engine, organization_id="mor")
    manifest = service.plan(request_key="plan", operator="operator", code_sha=SHA,
                            windows=windows or [(DAY, DAY)])
    return service, manifest, service.windows(manifest)[0]["id"]


def preview(service, window, records, key="preview"):
    return service.preview(window, request_key=key, operator="operator", code_sha=SHA, connector=Provider(records))


def rows(engine, table):
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(table)).mappings()]


def test_plan_retry_and_adjacent_windows(database):
    windows = [(DAY, DAY + timedelta(days=6)), (DAY + timedelta(days=7), DAY + timedelta(days=13))]
    service, manifest, _ = plan(database, windows)
    assert service.plan(request_key="plan", operator="operator", code_sha=SHA, windows=windows) == manifest
    assert len(rows(database, MANIFEST)) == 1
    assert len(service.windows(manifest)) == 2
    assert rows(database, MANIFEST)[0]["window_semantics"] == "dispatch_order_date"
    assert rows(database, MANIFEST)[0]["execution_mode"] == "preview_only"
    with pytest.raises(ControlError):
        service.plan(request_key="plan", operator="operator", code_sha=SHA, windows=[(DAY, DAY)])


@pytest.mark.parametrize("windows", [
    [(DAY, DAY), (DAY, DAY)], [(DAY, DAY + timedelta(days=6)), (DAY + timedelta(days=6), DAY + timedelta(days=7))],
    [(DAY, DAY + timedelta(days=7))], [(DAY, DAY - timedelta(days=1))], []])
def test_invalid_or_overlapping_window_rejected(database, windows):
    service = BackfillControl(database, organization_id="mor")
    with pytest.raises(ValueError):
        service.plan(request_key="invalid", operator="operator", code_sha=SHA, windows=windows)
    assert rows(database, MANIFEST) == []


def test_database_window_and_mode_constraints(database):
    _, manifest, window = plan(database)
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(update(WINDOW).where(WINDOW.c.id == window).values(date_to=DAY + timedelta(days=7)))
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(update(MANIFEST).where(MANIFEST.c.id == manifest).values(execution_mode="write"))


def test_tenant_isolation(database):
    _, manifest, window = plan(database)
    other = BackfillControl(database, organization_id="other")
    for action in (
        lambda: other.plan(request_key="other", operator="operator", code_sha=SHA, windows=[(DAY, DAY)]),
        lambda: other.windows(manifest),
        lambda: other.begin_preview(window, request_key="p", operator="operator", code_sha=SHA),
        lambda: other.approve(window, operator="operator"),
    ):
        with pytest.raises(ControlError):
            action()
    assert len(rows(database, MANIFEST)) == 1


def test_classification_and_scheduled_state_unchanged(database):
    seed(database, [dispatch(1, "A"), dispatch(2, "B")])
    baseline = snapshot(database)
    service, _, window = plan(database)
    result = preview(service, window, [dispatch(1, "A"), dispatch(2, "B", customerName="Changed"), dispatch(3, "C")])
    assert (result["would_insert"], result["would_update"], result["unchanged"]) == (1, 1, 1)
    assert snapshot(database) == baseline
    ledger = rows(database, ATTEMPT)[0]
    assert ledger["evidence"]["inserted"] == ledger["evidence"]["updated"] == 0
    assert ledger["claim_namespace"] == "torqueai_historical_preview"
    assert ledger["evidence_fingerprint"] == fingerprint(ledger["evidence"])
    assert rows(database, WINDOW)[0]["status"] == "previewed"
    service.approve(window, operator="owner")
    assert rows(database, WINDOW)[0]["status"] == "approved"
    with pytest.raises(ControlError):
        preview(service, window, [], key="new")
    assert snapshot(database) == baseline


def test_idempotent_preview_no_second_provider_call(database):
    service, _, window = plan(database)
    provider = Provider([dispatch(1, "A")])
    for _ in range(2):
        service.preview(window, request_key="p", operator="operator", code_sha=SHA, connector=provider)
    assert len(provider.calls) == 1
    assert len(rows(database, ATTEMPT)) == len(rows(database, IDENTITY)) == 1
    with pytest.raises(ControlError):
        service.begin_preview(window, request_key="p", operator="different", code_sha=SHA)


def test_separate_claim_and_expired_attempt_fencing(database):
    service, _, window = plan(database)
    attempt = service.begin_preview(window, request_key="first", operator="operator", code_sha=SHA)
    baseline = snapshot(database)
    with pytest.raises(ControlError):
        service.begin_preview(window, request_key="second", operator="operator", code_sha=SHA)
    with database.begin() as connection:
        connection.execute(update(WINDOW).where(WINDOW.c.id == window).values(lease_until=control_module.utcnow() - timedelta(seconds=1)))
    new_attempt = service.begin_preview(window, request_key="second", operator="operator", code_sha=SHA)
    assert new_attempt != attempt
    assert rows(database, ATTEMPT)[0]["status"] == "failed"
    assert snapshot(database) == baseline


def test_same_load_different_order_quarantined(database):
    seed(database, [dispatch(4882, "OLD")])
    service, _, window = plan(database)
    result = preview(service, window, [dispatch(4882, "NEW"), dispatch(4882, "THIRD")])
    assert result["identity_conflicts"] == 2
    assert result["would_insert"] == result["would_update"] == 0
    evidence = rows(database, IDENTITY)
    assert {row["provider_order_number"] for row in evidence} == {"NEW", "THIRD"}
    assert all(row["quarantined"] == 1 for row in evidence)
    assert rows(database, WINDOW)[0]["status"] == "blocked"
    with pytest.raises(ControlError):
        service.approve(window, operator="owner")
    with pytest.raises(ControlError):
        service.record_images(evidence[0]["id"], before_image=None, after_image={})


def test_failure_and_provider_bounds_preserved(database):
    service, _, window = plan(database)
    result = service.preview(window, request_key="overlimit", operator="operator", code_sha=SHA,
        connector=Provider([dispatch()], total=1001))
    assert result["status"] == "failed"
    assert result["validation_failures"] == [{"code": "ingestion_bound_exceeded"}]
    assert rows(database, WINDOW)[0]["status"] == "failed"
    assert rows(database, IDENTITY) == []
    preview(service, window, [dispatch()], key="retry")
    assert len(rows(database, ATTEMPT)) == 2


def test_missing_stops_and_ship_dates_outside_provider_window(database):
    service, _, window = plan(database)
    result = preview(service, window, [dispatch(shipDate="2025-06-30", orderDate=DAY.isoformat(), stops=[])])
    assert result["missing_usable_lane_stops"] == 1
    assert result["returned_ship_dates"]["outside_requested_window"] == 1
    assert rows(database, ATTEMPT)[0]["evidence"]["window_semantics"] == "dispatch_order_date"


def bundle(identity, changed=False):
    dispatch_image = {column.name: None for column in TorqueAIDispatch.__table__.columns}
    dispatch_image.update({column.name: "2025-06-01T00:00:00+00:00" for column in TorqueAIDispatch.__table__.columns
                           if not column.nullable and column.name.endswith("_at")})
    dispatch_image.update(id=123, organization_id=identity["organization_id"],
        provider_load_number=identity["provider_load_number"], provider_order_number=identity["provider_order_number"],
        customer_name="Changed" if changed else "Original", source_fingerprint="a" * 64)
    return {"dispatch": dispatch_image, "operational": None, "stops": []}


def test_before_after_integrity_and_conditional_rollback(database):
    seed(database, [dispatch(1, "A")])
    service, _, window = plan(database)
    preview(service, window, [dispatch(1, "A", customerName="Different")])
    identity = rows(database, IDENTITY)[0]
    before, after = bundle(identity), bundle(identity, True)
    baseline = snapshot(database)
    service.record_images(identity["id"], before_image=before, after_image=after)
    service.record_images(identity["id"], before_image=before, after_image=after)
    evidence = rows(database, IDENTITY)[0]
    assert evidence["before_fingerprint"] == fingerprint(before)
    assert evidence["after_fingerprint"] == fingerprint(after)
    assert rollback_eligible(evidence, after)
    changed = deepcopy(after)
    changed["dispatch"]["updated_at"] = "later-change-even-with-same-source-fingerprint"
    assert not rollback_eligible(evidence, changed)
    corrupt = deepcopy(evidence)
    corrupt["before_image"]["dispatch"]["customer_name"] = "tampered"
    assert not rollback_eligible(corrupt, after)
    corrupt = deepcopy(evidence)
    corrupt["after_fingerprint"] = "b" * 64
    assert not rollback_eligible(corrupt, after)
    with pytest.raises(ControlError):
        service.record_images(identity["id"], before_image=before, after_image=changed)
    assert snapshot(database) == baseline


def test_image_tenant_raw_payload_and_identity_rejected(database):
    service, _, window = plan(database)
    preview(service, window, [dispatch(1, "A")])
    identity = rows(database, IDENTITY)[0]
    for field, value in (("organization_id", "other"), ("provider_order_number", "different"), ("raw_payload", {})):
        image = bundle(identity)
        image["dispatch"][field] = value
        with pytest.raises(ControlError):
            service.record_images(identity["id"], before_image=None, after_image=image)
    assert rows(database, IDENTITY)[0]["after_fingerprint"] is None


def test_ledger_boundary_rejects_operational_and_checkpoint_mutation(database):
    for table in TABLES:
        with pytest.raises(ControlError), _ledger_connection(database) as connection:
            connection.execute(update(table).values({next(iter(table.c)).name: "forbidden"}))


def test_no_execution_entry_point():
    assert not hasattr(control_module, "main")
    assert not hasattr(BackfillControl, "run")
    assert not hasattr(BackfillControl, "rollback")
    source = inspect.getsource(control_module)
    assert "SessionLocal" not in source
    assert "ingest_torqueai_dispatches(" not in source
    assert "TorqueAIDispatchSyncState" not in source


def test_in_progress_retry_does_not_repeat_provider_request(database):
    service, _, window = plan(database)
    service.begin_preview(window, request_key="p", operator="operator", code_sha=SHA)
    provider = Provider([dispatch()])
    with pytest.raises(ControlError):
        service.preview(window, request_key="p", operator="operator", code_sha=SHA, connector=provider)
    assert provider.calls == []


def test_completion_evidence_immutable_and_lost_claim_fenced(database):
    service, _, window = plan(database)
    report = preview(service, window, [dispatch()])
    attempt = rows(database, ATTEMPT)[0]
    assert service.finish_preview(window, attempt["id"], report) == "previewed"
    changed = deepcopy(report)
    changed["returned_ship_dates"]["maximum"] = "2025-07-01"
    with pytest.raises(ControlError):
        service.finish_preview(window, attempt["id"], changed)
    assert len(rows(database, IDENTITY)) == 1
    old = service.begin_preview(window, request_key="old", operator="operator", code_sha=SHA)
    with database.begin() as connection:
        connection.execute(update(WINDOW).where(WINDOW.c.id == window).values(lease_until=control_module.utcnow() - timedelta(seconds=1)))
    service.begin_preview(window, request_key="new", operator="operator", code_sha=SHA)
    with pytest.raises(ControlError):
        service.finish_preview(window, old, report)


def test_invalid_completion_rolls_back_without_publishing_evidence(database):
    service, _, window = plan(database)
    attempt = service.begin_preview(window, request_key="p", operator="operator", code_sha=SHA)
    from app.connectors.torqueai_history_preview import preview_torqueai_history
    report = preview_torqueai_history(database, date_from=DAY, date_to=DAY, connector=Provider([dispatch()]))
    for modify in (
        lambda r: r.update(database_writes=True),
        lambda r: r.update(request={"from": "2025-05-31", "to": "2025-06-01"}),
        lambda r: r.update(would_insert=3),
    ):
        invalid = deepcopy(report)
        modify(invalid)
        with pytest.raises(ControlError):
            service.finish_preview(window, attempt, invalid)
        assert rows(database, IDENTITY) == []
        assert rows(database, ATTEMPT)[0]["completed_at"] is None


def test_insert_images_and_later_stop_change_refuses_rollback(database):
    service, _, window = plan(database)
    preview(service, window, [dispatch()])
    identity = rows(database, IDENTITY)[0]
    image = bundle(identity)
    service.record_images(identity["id"], before_image=None, after_image=image)
    evidence = rows(database, IDENTITY)[0]
    assert rollback_eligible(evidence, image)
    assert evidence["before_image"] is None
    stop = {column.name: None for column in TorqueAIDispatchStop.__table__.columns}
    stop.update({column.name: "2025-06-01T00:00:00+00:00" for column in TorqueAIDispatchStop.__table__.columns
                 if not column.nullable and column.name.endswith("_at")})
    stop.update(id=1, organization_id="mor", dispatch_id=123, stop_index=0, city="Changed")
    stop["source_fingerprint"] = "a" * 64
    later = deepcopy(image)
    later["stops"].append(stop)
    assert not rollback_eligible(evidence, later)
    other = BackfillControl(database, organization_id="other")
    with pytest.raises(ControlError):
        other.record_images(identity["id"], before_image=None, after_image=image)


def test_database_duplicate_interval_and_cross_tenant_fk(database):
    service, manifest, window = plan(database)
    existing = rows(database, WINDOW)[0]
    existing["id"] = "duplicate"
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(insert(WINDOW).values(**existing))
    existing["organization_id"] = "other"
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(insert(WINDOW).values(**existing))


def test_frozen_migration_schema_matches_runtime_and_postgres_compiles():
    import importlib.util
    from pathlib import Path
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    migration = Path(__file__).resolve().parents[1] / "migrations/versions/202610070001_torqueai_backfill_control_plane.py"
    spec = importlib.util.spec_from_file_location("control_migration", migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for current, frozen in zip((MANIFEST, WINDOW, ATTEMPT, IDENTITY), module._tables()):
        current_sql = str(CreateTable(current).compile(dialect=postgresql.dialect()))
        frozen_sql = str(CreateTable(frozen).compile(dialect=postgresql.dialect()))
        assert current_sql == frozen_sql
        if current is WINDOW:
            assert "date_to - date_from <= 6" in current_sql
            assert "julianday" not in current_sql


def test_retry_cannot_clear_historical_identity_quarantine(database):
    seed(database, [dispatch(4882, "OLD")])
    service, _, window = plan(database)
    preview(service, window, [dispatch(4882, "NEW")])
    assert rows(database, WINDOW)[0]["status"] == "blocked"
    preview(service, window, [], key="later-with-conflict-absent")
    assert rows(database, WINDOW)[0]["status"] == "blocked"
    assert len(rows(database, IDENTITY)) == 1
    with pytest.raises(ControlError):
        service.approve(window, operator="owner")


def test_duplicate_and_overlapping_windows_across_manifests_forbidden(database):
    service, _, window = plan(database, [(DAY, DAY + timedelta(days=6))])
    for start, end in ((DAY, DAY + timedelta(days=6)), (DAY + timedelta(days=3), DAY + timedelta(days=8))):
        with pytest.raises(ControlError):
            service.plan(request_key="second-plan", operator="operator", code_sha=SHA, windows=[(start, end)])
    assert len(rows(database, MANIFEST)) == len(rows(database, WINDOW)) == 1
    manifest = service.plan(request_key="adjacent-plan", operator="operator", code_sha=SHA,
        windows=[(DAY + timedelta(days=7), DAY + timedelta(days=13))])
    assert len(service.windows(manifest)) == 1
