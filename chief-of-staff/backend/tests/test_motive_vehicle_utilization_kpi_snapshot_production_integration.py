from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from app.motive import vehicle_utilization_kpi_snapshot_production as snapshot_production
from app.motive import vehicle_utilization_production_ingestion as production
from app.motive.vehicle_utilization_writer import VehicleUtilizationWriteResult


FLAG = production.PRODUCTION_INGESTION_ENABLED_ENV_VAR


def _enable(monkeypatch):
    monkeypatch.setenv(FLAG, "true")


@contextmanager
def _unlocked(**kwargs):
    yield


def _write_result(*, returned=1, missing=2, inserted=1, unchanged=0, updated=0, reconciled=0):
    return VehicleUtilizationWriteResult(
        committed=True,
        requested_vehicle_count=3,
        returned_rollup_count=returned,
        records_inserted=inserted,
        records_unchanged=unchanged,
        records_updated=updated,
        missing_requested_vehicle_count=missing,
        reconciled_fields_count=reconciled,
    )


def _patch_success_path(monkeypatch, *, events=None):
    events = events if events is not None else []
    read_calls = []
    monkeypatch.setattr(production, "_organization_run_lock", _unlocked)
    monkeypatch.setattr(
        production,
        "_checkpoint_snapshot",
        lambda *a, **k: {"status": "not_started", "completed_through": None},
    )
    monkeypatch.setattr(production, "_select_provider_vehicle_ids", lambda *a, **k: ["v1", "v2", "v3"])

    def read(**kwargs):
        read_calls.append(kwargs)
        events.append("provider")
        return [SimpleNamespace(provider_vehicle_id="v1", metric_units=False)]

    def writer(*args, **kwargs):
        events.append("writer")
        return _write_result()

    monkeypatch.setattr(production, "_read_one_production_page", read)
    monkeypatch.setattr(production, "write_vehicle_utilization_transaction", writer)
    return read_calls


def test_success_persists_one_snapshot_after_metadata_with_exact_run_context(monkeypatch):
    _enable(monkeypatch)
    events = []
    read_calls = _patch_success_path(monkeypatch, events=events)
    snapshot_calls = []

    def persist_metadata(*args, **kwargs):
        events.append("metadata")
        return True, True

    def history_id(*args, **kwargs):
        events.append("history")
        return 42

    def snapshot(**kwargs):
        events.append("snapshot")
        snapshot_calls.append(kwargs)

    monkeypatch.setattr(production, "_persist_history_and_checkpoint", persist_metadata)
    monkeypatch.setattr(production, "_successful_history_id", history_id)
    monkeypatch.setattr(snapshot_production, "persist_vehicle_utilization_kpi_snapshot_after_success", snapshot)

    sentinel_factory = lambda: object()
    result = production.run_vehicle_utilization_production_ingestion(
        object(),
        organization_id="org",
        organization_slug="slug",
        snapshot_session_factory=sentinel_factory,
        end_date=date(2026, 8, 18),
    )

    assert result.status == "success"
    assert result.provider_calls_attempted == 7
    assert result.provider_calls_completed == 7
    assert len(read_calls) == 7
    assert len(snapshot_calls) == 1
    assert events.index("metadata") < events.index("history") < events.index("snapshot")
    assert snapshot_calls[0]["session_factory"] is sentinel_factory
    assert snapshot_calls[0]["organization_id"] == "org"
    assert snapshot_calls[0]["organization_slug"] == "slug"
    assert snapshot_calls[0]["selected_provider_vehicle_ids"] == ("v1", "v2", "v3")
    assert snapshot_calls[0]["window_end"] == date(2026, 8, 18)
    assert snapshot_calls[0]["source_history_id"] == 42


def test_partial_success_never_attempts_snapshot(monkeypatch):
    _enable(monkeypatch)
    _patch_success_path(monkeypatch)
    call_number = 0
    snapshot_called = False

    def read(**kwargs):
        nonlocal call_number
        call_number += 1
        if call_number == 3:
            raise production.MotiveVehicleUtilizationPaginationError("provider_failure", "safe")
        return [SimpleNamespace(provider_vehicle_id="v1", metric_units=False)]

    def persist_metadata(*args, **kwargs):
        return True, False

    def snapshot(**kwargs):
        nonlocal snapshot_called
        snapshot_called = True

    monkeypatch.setattr(production, "_read_one_production_page", read)
    monkeypatch.setattr(production, "_persist_history_and_checkpoint", persist_metadata)
    monkeypatch.setattr(
        production,
        "_successful_history_id",
        lambda *a, **k: pytest.fail("partial success must not resolve snapshot lineage"),
    )
    monkeypatch.setattr(snapshot_production, "persist_vehicle_utilization_kpi_snapshot_after_success", snapshot)

    result = production.run_vehicle_utilization_production_ingestion(
        object(), organization_id="org", organization_slug="slug", end_date=date(2026, 8, 18)
    )

    assert result.status == "partial_success"
    assert result.provider_calls_attempted == 7
    assert snapshot_called is False


def test_snapshot_failure_is_isolated_from_success_and_does_not_retry_provider(monkeypatch, caplog):
    _enable(monkeypatch)
    read_calls = _patch_success_path(monkeypatch)
    monkeypatch.setattr(production, "_persist_history_and_checkpoint", lambda *a, **k: (True, True))
    monkeypatch.setattr(production, "_successful_history_id", lambda *a, **k: 77)

    def snapshot(**kwargs):
        raise RuntimeError("provider-secret-value")

    monkeypatch.setattr(snapshot_production, "persist_vehicle_utilization_kpi_snapshot_after_success", snapshot)

    with caplog.at_level("ERROR"):
        result = production.run_vehicle_utilization_production_ingestion(
            object(), organization_id="org", organization_slug="slug", end_date=date(2026, 8, 18)
        )

    assert result.status == "success"
    assert result.checkpoint_advanced is True
    assert result.sync_history_written is True
    assert result.provider_calls_attempted == 7
    assert result.provider_calls_completed == 7
    assert len(read_calls) == 7
    assert "KPI SNAPSHOT PERSISTENCE FAILED" in caplog.text
    assert "provider-secret-value" not in caplog.text


class _FakeSnapshotSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def test_snapshot_helper_uses_one_separate_local_transaction(monkeypatch):
    session = _FakeSnapshotSession()
    observed = {}
    rows = [object()]
    computation = object()

    def load(candidate_session, **kwargs):
        assert candidate_session is session
        observed["load"] = kwargs
        return rows

    def calculate(**kwargs):
        observed["calculate"] = kwargs
        assert kwargs["rows"] is rows
        return computation

    def upsert(candidate_session, **kwargs):
        assert candidate_session is session
        observed["upsert"] = kwargs
        assert kwargs["computation"] is computation

    monkeypatch.setattr(snapshot_production, "load_vehicle_utilization_snapshot_rows", load)
    monkeypatch.setattr(snapshot_production, "calculate_vehicle_utilization_kpi_snapshot", calculate)
    monkeypatch.setattr(snapshot_production, "upsert_vehicle_utilization_kpi_snapshot", upsert)

    snapshot_production.persist_vehicle_utilization_kpi_snapshot_after_success(
        session_factory=lambda: session,
        organization_id="org",
        organization_slug="slug",
        selected_provider_vehicle_ids=("v1", "v2", "v3"),
        window_end=date(2026, 8, 18),
        source_history_id=123,
    )

    assert observed["load"]["selected_provider_vehicle_ids"] == ("v1", "v2", "v3")
    assert observed["calculate"]["selected_provider_vehicle_ids"] == ("v1", "v2", "v3")
    assert observed["upsert"]["source_history_id"] == 123
    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.closes == 1


def test_snapshot_helper_rolls_back_and_raises_only_sanitized_error(monkeypatch):
    session = _FakeSnapshotSession()

    def fail(*args, **kwargs):
        raise RuntimeError("provider-secret-value")

    monkeypatch.setattr(snapshot_production, "load_vehicle_utilization_snapshot_rows", fail)

    with pytest.raises(snapshot_production.MotiveVehicleUtilizationKpiSnapshotProductionError) as exc:
        snapshot_production.persist_vehicle_utilization_kpi_snapshot_after_success(
            session_factory=lambda: session,
            organization_id="org",
            organization_slug="slug",
            selected_provider_vehicle_ids=("v1",),
            window_end=date(2026, 8, 18),
            source_history_id=123,
        )

    assert str(exc.value) == "Motive vehicle-utilization KPI snapshot persistence failed."
    assert "provider-secret-value" not in str(exc.value)
    assert session.commits == 0
    assert session.rollbacks == 1
    assert session.closes == 1
