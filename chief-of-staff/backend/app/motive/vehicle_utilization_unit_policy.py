"""Canonical unit policy for future Motive vehicle-utilization writes.

The current verifier and bounded-evidence probes may still use their existing
environment-controlled request boundary. Durable writer enablement must use the
fixed Polaris-owned policy below instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS = True
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE = "true"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM = "metric"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER = "X-Metric-Units"
MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED = False


@dataclass(frozen=True, slots=True)
class VehicleUtilizationMetricUnitsValidation:
    valid: bool
    error_code: str | None = None


def vehicle_utilization_writer_metric_units_header_value(metric_units: bool) -> str:
    """Return Motive's Boolean header spelling for an explicit unit mode."""
    return "true" if metric_units is True else "false"


def validate_vehicle_utilization_writer_metric_units(
    returned_metric_units: Any,
) -> VehicleUtilizationMetricUnitsValidation:
    """Fail closed unless Motive returns the certified canonical unit context."""
    if returned_metric_units is True:
        return VehicleUtilizationMetricUnitsValidation(valid=True)
    if returned_metric_units is False:
        return VehicleUtilizationMetricUnitsValidation(
            valid=False,
            error_code="provider_unit_policy_mismatch",
        )
    if returned_metric_units is None:
        return VehicleUtilizationMetricUnitsValidation(
            valid=False,
            error_code="provider_unit_context_missing",
        )
    return VehicleUtilizationMetricUnitsValidation(
        valid=False,
        error_code="provider_unit_context_invalid_type",
    )
