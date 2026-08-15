from __future__ import annotations

import os

import pytest

from app.motive.vehicle_utilization_unit_policy import (
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
    validate_vehicle_utilization_writer_metric_units,
    vehicle_utilization_writer_metric_units_header_value,
)


def test_vehicle_utilization_canonical_writer_policy_is_metric() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS is True
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE == "true"
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM == "metric"
    assert MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED is False


def test_vehicle_utilization_canonical_writer_policy_does_not_read_probe_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLARIS_MOTIVE_X_METRIC_UNITS", "false")

    assert os.getenv("POLARIS_MOTIVE_X_METRIC_UNITS") == "false"
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS is True
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE == "true"


@pytest.mark.parametrize(
    ("metric_units", "expected_header"),
    [(True, "true"), (False, "false")],
)
def test_vehicle_utilization_explicit_metric_units_header_value(metric_units: bool, expected_header: str) -> None:
    assert vehicle_utilization_writer_metric_units_header_value(metric_units) == expected_header


@pytest.mark.parametrize("metric_units", [1, 0, "true", "false", "metric", "imperial", []])
def test_vehicle_utilization_explicit_metric_units_header_value_rejects_non_boolean(metric_units: object) -> None:
    with pytest.raises(ValueError, match="explicit Boolean"):
        vehicle_utilization_writer_metric_units_header_value(metric_units)  # type: ignore[arg-type]


def test_vehicle_utilization_writer_metric_units_validator_accepts_true() -> None:
    result = validate_vehicle_utilization_writer_metric_units(True)

    assert result.valid is True
    assert result.error_code is None


@pytest.mark.parametrize(
    ("returned_metric_units", "expected_error_code"),
    [
        (False, "provider_unit_policy_mismatch"),
        (None, "provider_unit_context_missing"),
        ("true", "provider_unit_context_invalid_type"),
        (1, "provider_unit_context_invalid_type"),
        ("metric", "provider_unit_context_invalid_type"),
    ],
)
def test_vehicle_utilization_writer_metric_units_validator_fails_closed(
    returned_metric_units: object,
    expected_error_code: str,
) -> None:
    result = validate_vehicle_utilization_writer_metric_units(returned_metric_units)

    assert result.valid is False
    assert result.error_code == expected_error_code
