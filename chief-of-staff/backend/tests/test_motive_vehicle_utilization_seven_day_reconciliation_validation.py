from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api import motive_seven_day_reconciliation_validation as api
from app.motive import vehicle_utilization_seven_day_reconciliation_validation as validation
from app.motive.vehicle_utilization_recent_reconciliation import (
    FailedReconciliationUnit,
    VehicleUtilizationRecentReconciliationResult,
)

RUNNER_FLAG = "MOTIVE_VEHICLE_UTILIZATION_RECENT_RECONCILIATION_ENABLED"
SEVEN_DAY_FLAG = validation.SEVEN_DAY_RECONCILIATION_VALIDATION_ENABLED_ENV_VAR


def _result(*, status="success", calls=7, completed=7, failed=0, failed_units=()):
    return VehicleUtilizationRecentReconciliationResult(
        status=status,
        resource="vehicle_utilization_recent_window_reconciliation",
        run_mode="bounded_manual_recent_window_reconciliation",
        horizon_days=7,
        windows_attempted=7,
        windows_completed=completed,
        windows_failed=failed,
        selected_vehicle_count=23,
        vehicle_batches_attempted=7,
        vehicle_batches_completed=completed,
        vehicle_batches_failed=failed,
        provider_calls_attempted=calls,
        provider_calls_completed=max(0, calls - failed),
        rollups_returned=40,
        missing_requested_vehicle_count=121,
        records_inserted=30,
        records_unchanged=10,
        records_updated=0,
        reconciled_fields_count=0,
        failed_units=failed_units,
    )


def _enable(monkeypatch):
    monkeypatch.setenv(RUNNER_FLAG, "true")
    monkeypatch.setenv(SEVEN_DAY_FLAG, "true")


def test_seven_day_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(SEVEN_DAY_FLAG, raising=False)
    assert validation.seven_day_reconciliation_validation_enabled() is False


def test_disabled_gate_fails_before_selection(monkeypatch):
    monkeypatch.setenv(RUNNER_FLAG, "true")
    monkeypatch.delenv(SEVEN_DAY_FLAG, raising=False)
    selected = False

    def select(*args, **kwargs):
        nonlocal selected
        selected = True
        return []

    monkeypatch.setattr(validation, "_select_tenant_vehicles", select)
    with pytest.raises(validation.MotiveVehicleUtilizationSevenDayReconciliationValidationError) as exc:
        validation.run_seven_day_vehicle_utilization_reconciliation_live_validation(
            object(), organization_id="org", organization_slug="slug"
        )
    assert exc.value.code == "seven_day_reconciliation_validation_disabled"
    assert selected is False


def test_101_vehicles_fail_before_runner(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(validation, "_select_tenant_vehicles", lambda *args, **kwargs: [object()] * 101)
    runner_called = False

    def runner(*args, **kwargs):
        nonlocal runner_called
        runner_called = True
        return _result()

    monkeypatch.setattr(validation, "run_recent_vehicle_utilization_reconciliation", runner)
    with pytest.raises(validation.MotiveVehicleUtilizationSevenDayReconciliationValidationError) as exc:
        validation.run_seven_day_vehicle_utilization_reconciliation_live_validation(
            object(), organization_id="org", organization_slug="slug"
        )
    assert exc.value.code == "seven_day_validation_vehicle_limit_exceeded"
    assert exc.value.sanitized_context["provider_calls_attempted"] == 0
    assert runner_called is False


def test_success_hardcodes_seven_days_and_sanitizes(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(validation, "_select_tenant_vehicles", lambda *args, **kwargs: [object()] * 23)
    observed = {}

    def runner(*args, **kwargs):
        observed.update(kwargs)
        return _result()

    monkeypatch.setattr(validation, "run_recent_vehicle_utilization_reconciliation", runner)
    result = validation.run_seven_day_vehicle_utilization_reconciliation_live_validation(
        object(), organization_id="org", organization_slug="slug"
    )
    assert observed["horizon_days"] == 7
    assert result["status"] == "success"
    assert result["horizon_days"] == 7
    assert result["provider_calls_attempted"] == 7
    assert result["checkpoint_advanced"] is False
    assert result["sync_history_written"] is False
    assert result["scheduled_ingestion_enabled"] is False
    assert result["secrets_exposed"] is False
    forbidden = {"provider_vehicle_id", "vin", "raw_payload", "api_key", "bearer_token", "organization_id"}
    assert forbidden.isdisjoint(result.keys())


def test_posthoc_call_budget_violation_fails_closed(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(validation, "_select_tenant_vehicles", lambda *args, **kwargs: [object()])
    monkeypatch.setattr(validation, "run_recent_vehicle_utilization_reconciliation", lambda *a, **k: _result(calls=8))
    with pytest.raises(validation.MotiveVehicleUtilizationSevenDayReconciliationValidationError) as exc:
        validation.run_seven_day_vehicle_utilization_reconciliation_live_validation(
            object(), organization_id="org", organization_slug="slug"
        )
    assert exc.value.code == "seven_day_provider_call_budget_invariant_violated"


def test_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        api.VehicleUtilizationSevenDayReconciliationValidationRequest(confirm=True, horizon_days=14)


def test_api_partial_success_returns_207(monkeypatch):
    monkeypatch.setattr(api, "recent_reconciliation_enabled", lambda: True)
    monkeypatch.setattr(api, "seven_day_reconciliation_validation_enabled", lambda: True)
    monkeypatch.setattr(api, "_organization", lambda *args, **kwargs: SimpleNamespace(slug="slug"))
    failed_unit = {
        "window_start": "2026-08-12",
        "window_end": "2026-08-12",
        "batch_ordinal": 1,
        "error_code": "provider_failure",
    }
    payload = validation._sanitized_response(
        _result(
            status="partial_success",
            calls=7,
            completed=6,
            failed=1,
            failed_units=(FailedReconciliationUnit(**failed_unit),),
        )
    )
    monkeypatch.setattr(api, "run_seven_day_vehicle_utilization_reconciliation_live_validation", lambda *a, **k: payload)
    response = Response()
    result = api.verify_motive_vehicle_utilization_recent_reconciliation_seven_day(
        response=response,
        body=api.VehicleUtilizationSevenDayReconciliationValidationRequest(confirm=True),
        principal=SimpleNamespace(organization_id="org"),
        session=object(),
    )
    assert response.status_code == 207
    assert result["status"] == "partial_success"
    assert result["failed_units"] == [failed_unit]


def test_api_all_safe_failures_map_to_502(monkeypatch):
    monkeypatch.setattr(api, "recent_reconciliation_enabled", lambda: True)
    monkeypatch.setattr(api, "seven_day_reconciliation_validation_enabled", lambda: True)
    monkeypatch.setattr(api, "_organization", lambda *args, **kwargs: SimpleNamespace(slug="slug"))
    payload = validation._sanitized_response(
        _result(
            status="failed",
            calls=7,
            completed=0,
            failed=7,
            failed_units=(
                FailedReconciliationUnit(
                    window_start="2026-08-12",
                    window_end="2026-08-12",
                    batch_ordinal=1,
                    error_code="provider_failure",
                ),
            ),
        )
    )
    monkeypatch.setattr(api, "run_seven_day_vehicle_utilization_reconciliation_live_validation", lambda *a, **k: payload)
    with pytest.raises(HTTPException) as exc:
        api.verify_motive_vehicle_utilization_recent_reconciliation_seven_day(
            response=Response(),
            body=api.VehicleUtilizationSevenDayReconciliationValidationRequest(confirm=True),
            principal=SimpleNamespace(organization_id="org"),
            session=object(),
        )
    assert exc.value.status_code == 502
    assert exc.value.detail["error_code"] == "provider_failure"
    assert exc.value.detail["secrets_exposed"] is False


def test_api_confirmation_required_before_organization_lookup(monkeypatch):
    monkeypatch.setattr(api, "recent_reconciliation_enabled", lambda: True)
    monkeypatch.setattr(api, "seven_day_reconciliation_validation_enabled", lambda: True)
    looked_up = False

    def lookup(*args, **kwargs):
        nonlocal looked_up
        looked_up = True
        return SimpleNamespace(slug="slug")

    monkeypatch.setattr(api, "_organization", lookup)
    with pytest.raises(HTTPException) as exc:
        api.verify_motive_vehicle_utilization_recent_reconciliation_seven_day(
            response=Response(),
            body=api.VehicleUtilizationSevenDayReconciliationValidationRequest(confirm=False),
            principal=SimpleNamespace(organization_id="org"),
            session=object(),
        )
    assert exc.value.status_code == 400
    assert looked_up is False
