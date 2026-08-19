from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api import motive_vehicle_utilization_production as api
from app.motive import vehicle_utilization_production_ingestion as production
from app.motive.vehicle_utilization_unit_policy import MotiveVehicleUtilizationUnitRequestMode
from app.motive.vehicle_utilization_writer import VehicleUtilizationWriteResult


FLAG = production.PRODUCTION_INGESTION_ENABLED_ENV_VAR


def _enable(monkeypatch):
    monkeypatch.setenv(FLAG, "true")


@contextmanager
def _unlocked(**kwargs):
    yield


def _write_result(*, returned=2, missing=1, inserted=1, unchanged=0, updated=1, reconciled=2):
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


def _patch_common(monkeypatch, *, ids=None):
    monkeypatch.setattr(production, "_organization_run_lock", _unlocked)
    monkeypatch.setattr(production, "_checkpoint_snapshot", lambda *a, **k: {"status": "not_started", "completed_through": None})
    monkeypatch.setattr(production, "_select_provider_vehicle_ids", lambda *a, **k: ids or ["v1", "v2", "v3"])


def test_production_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert production.production_ingestion_enabled() is False


def test_production_contract_is_explicit_imperial_and_chicago():
    assert production.PRODUCTION_TIME_ZONE == "America/Chicago"
    assert production.PRODUCTION_UNIT_REQUEST_MODE is MotiveVehicleUtilizationUnitRequestMode.IMPERIAL
    assert production.PRODUCTION_FUEL_UNIT == "gallons"
    assert production.PRODUCTION_MAX_VEHICLES == 100
    assert production.PRODUCTION_MAX_PROVIDER_CALLS == 7


def test_day_windows_are_exactly_seven_completed_days_oldest_first():
    windows = production._day_windows(end_date=date(2026, 8, 18))
    assert len(windows) == 7
    assert windows[0] == (date(2026, 8, 12), date(2026, 8, 12))
    assert windows[-1] == (date(2026, 8, 18), date(2026, 8, 18))
    assert all(start == end for start, end in windows)


def test_disabled_gate_fails_before_lock_or_provider(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    locked = False

    @contextmanager
    def lock(**kwargs):
        nonlocal locked
        locked = True
        yield

    monkeypatch.setattr(production, "_organization_run_lock", lock)
    with pytest.raises(production.MotiveVehicleUtilizationProductionIngestionError) as exc:
        production.run_vehicle_utilization_production_ingestion(
            object(), organization_id="org", organization_slug="slug", end_date=date(2026, 8, 18)
        )
    assert exc.value.code == "production_ingestion_disabled"
    assert locked is False


def test_vehicle_limit_fails_before_provider(monkeypatch):
    class Query:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def all(self):
            return [SimpleNamespace(provider_vehicle_id=f"v{i}") for i in range(101)]

    class Session:
        def query(self, *args, **kwargs):
            return Query()

    with pytest.raises(production.MotiveVehicleUtilizationProductionIngestionError) as exc:
        production._select_provider_vehicle_ids(Session(), "org")
    assert exc.value.code == "production_vehicle_limit_exceeded"


def test_one_page_reader_sends_explicit_imperial_and_refuses_page_two(monkeypatch):
    observed = {}

    def request(**kwargs):
        observed.update(kwargs)
        return {
            "pagination": {"per_page": 100, "page_no": 1, "total": 101},
            "vehicle_idle_rollups": [],
        }, 200

    monkeypatch.setattr(production, "request_vehicle_utilization_page", request)
    with pytest.raises(production.MotiveVehicleUtilizationPaginationError) as exc:
        production._read_one_production_page(
            organization_id="org",
            organization_slug="slug",
            provider_vehicle_ids=["v1"],
            window_start=date(2026, 8, 18),
            window_end=date(2026, 8, 18),
        )
    assert exc.value.code == "production_pagination_requires_second_page"
    assert observed["page_no"] == 1
    assert observed["per_page"] == 100
    assert observed["unit_request_mode"] is MotiveVehicleUtilizationUnitRequestMode.IMPERIAL
    assert "metric_units" not in observed


def test_success_uses_seven_calls_writes_history_once_and_advances_checkpoint(monkeypatch):
    _enable(monkeypatch)
    _patch_common(monkeypatch)
    read_calls = []
    writer_calls = []
    metadata_calls = []

    def read(**kwargs):
        read_calls.append(kwargs)
        return [SimpleNamespace(provider_vehicle_id="v1", metric_units=False)]

    def writer(*args, **kwargs):
        writer_calls.append(kwargs)
        return _write_result(returned=1, missing=2, inserted=1, updated=0, reconciled=0)

    def persist(*args, **kwargs):
        metadata_calls.append(kwargs)
        return True, True

    monkeypatch.setattr(production, "_read_one_production_page", read)
    monkeypatch.setattr(production, "write_vehicle_utilization_transaction", writer)
    monkeypatch.setattr(production, "_persist_history_and_checkpoint", persist)

    result = production.run_vehicle_utilization_production_ingestion(
        object(), organization_id="org", organization_slug="slug", end_date=date(2026, 8, 18)
    )

    assert result.status == "success"
    assert result.windows_attempted == 7
    assert result.windows_completed == 7
    assert result.provider_calls_attempted == 7
    assert result.provider_calls_completed == 7
    assert result.checkpoint_advanced is True
    assert result.sync_history_written is True
    assert result.scheduled_ingestion_enabled is False
    assert len(read_calls) == 7
    assert len(writer_calls) == 7
    assert len(metadata_calls) == 1
    assert all(call["unit_request_mode"] is MotiveVehicleUtilizationUnitRequestMode.IMPERIAL for call in writer_calls)
    assert all(call["window_start"] == call["window_end"] for call in read_calls)
    assert metadata_calls[0]["result_status"] == "success"
    assert metadata_calls[0]["completed_through"] == date(2026, 8, 18)


def test_partial_success_keeps_processing_but_does_not_advance_checkpoint(monkeypatch):
    _enable(monkeypatch)
    _patch_common(monkeypatch)
    call_number = 0
    metadata_calls = []

    def read(**kwargs):
        nonlocal call_number
        call_number += 1
        if call_number == 3:
            raise production.MotiveVehicleUtilizationPaginationError("provider_failure", "safe")
        return [SimpleNamespace(provider_vehicle_id="v1", metric_units=False)]

    monkeypatch.setattr(production, "_read_one_production_page", read)
    monkeypatch.setattr(production, "write_vehicle_utilization_transaction", lambda *a, **k: _write_result(returned=1, missing=2, inserted=0, unchanged=1, updated=0, reconciled=0))

    def persist(*args, **kwargs):
        metadata_calls.append(kwargs)
        return True, False

    monkeypatch.setattr(production, "_persist_history_and_checkpoint", persist)

    result = production.run_vehicle_utilization_production_ingestion(
        object(), organization_id="org", organization_slug="slug", end_date=date(2026, 8, 18)
    )
    assert result.status == "partial_success"
    assert result.windows_completed == 6
    assert result.windows_failed == 1
    assert result.provider_calls_attempted == 7
    assert result.checkpoint_advanced is False
    assert result.sync_history_written is True
    assert len(result.failed_units) == 1
    assert result.failed_units[0].error_code == "provider_failure"
    assert len(metadata_calls) == 1
    assert metadata_calls[0]["result_status"] == "partial_success"


def test_concurrent_run_fails_before_provider(monkeypatch):
    _enable(monkeypatch)
    called = False

    @contextmanager
    def busy(**kwargs):
        raise production.MotiveVehicleUtilizationProductionIngestionError(
            "production_run_already_in_progress", "busy"
        )
        yield

    def read(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(production, "_organization_run_lock", busy)
    monkeypatch.setattr(production, "_read_one_production_page", read)
    with pytest.raises(production.MotiveVehicleUtilizationProductionIngestionError) as exc:
        production.run_vehicle_utilization_production_ingestion(
            object(), organization_id="org", organization_slug="slug", end_date=date(2026, 8, 18)
        )
    assert exc.value.code == "production_run_already_in_progress"
    assert called is False


def test_result_shape_contains_no_provider_identity_or_secret_fields(monkeypatch):
    result = production.ProductionIngestionResult(
        status="success",
        resource="vehicle_utilization",
        run_mode="production_recent_window_ingestion",
        horizon_days=7,
        request_timezone="America/Chicago",
        unit_request_mode="imperial",
        fuel_unit="gallons",
        x_metric_units=False,
        selected_vehicle_count=3,
        windows_attempted=7,
        windows_completed=7,
        windows_failed=0,
        provider_calls_attempted=7,
        provider_calls_completed=7,
        rollups_returned=10,
        missing_requested_vehicle_count=11,
        records_inserted=5,
        records_unchanged=3,
        records_updated=2,
        reconciled_fields_count=4,
        checkpoint_advanced=True,
        sync_history_written=True,
    ).as_dict()
    forbidden = {"provider_vehicle_id", "vin", "raw_payload", "api_key", "bearer_token", "organization_id"}
    assert forbidden.isdisjoint(result.keys())
    assert result["scheduled_ingestion_enabled"] is False
    assert result["secrets_exposed"] is False


def test_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        api.VehicleUtilizationProductionIngestionRequest(confirm=True, horizon_days=14)


def test_api_confirmation_required_before_organization_lookup(monkeypatch):
    monkeypatch.setattr(api, "production_ingestion_enabled", lambda: True)
    looked_up = False

    def lookup(*args, **kwargs):
        nonlocal looked_up
        looked_up = True
        return SimpleNamespace(slug="slug")

    monkeypatch.setattr(api, "_organization", lookup)
    with pytest.raises(HTTPException) as exc:
        api.sync_motive_vehicle_utilization_production(
            response=Response(),
            body=api.VehicleUtilizationProductionIngestionRequest(confirm=False),
            principal=SimpleNamespace(organization_id="org"),
            session=object(),
        )
    assert exc.value.status_code == 400
    assert looked_up is False


def test_api_partial_success_returns_207(monkeypatch):
    monkeypatch.setattr(api, "production_ingestion_enabled", lambda: True)
    monkeypatch.setattr(api, "_organization", lambda *a, **k: SimpleNamespace(slug="slug"))
    payload = production.ProductionIngestionResult(
        status="partial_success",
        resource="vehicle_utilization",
        run_mode="production_recent_window_ingestion",
        horizon_days=7,
        request_timezone="America/Chicago",
        unit_request_mode="imperial",
        fuel_unit="gallons",
        x_metric_units=False,
        selected_vehicle_count=3,
        windows_attempted=7,
        windows_completed=6,
        windows_failed=1,
        provider_calls_attempted=7,
        provider_calls_completed=6,
        rollups_returned=10,
        missing_requested_vehicle_count=11,
        records_inserted=5,
        records_unchanged=3,
        records_updated=2,
        reconciled_fields_count=4,
        checkpoint_advanced=False,
        sync_history_written=True,
        failed_units=(
            production.FailedProductionWindow("2026-08-16", "2026-08-16", "provider_failure"),
        ),
    )
    monkeypatch.setattr(api, "run_vehicle_utilization_production_ingestion", lambda *a, **k: payload)
    response = Response()
    result = api.sync_motive_vehicle_utilization_production(
        response=response,
        body=api.VehicleUtilizationProductionIngestionRequest(confirm=True),
        principal=SimpleNamespace(organization_id="org"),
        session=object(),
    )
    assert response.status_code == 207
    assert result["status"] == "partial_success"
    assert result["checkpoint_advanced"] is False
