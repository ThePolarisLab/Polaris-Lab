"""Canonical unit policy for future Motive vehicle-utilization writes.

The current verifier and bounded-evidence probes may still use their existing
environment-controlled request boundary. Durable writer enablement must use the
fixed Polaris-owned policy below instead.

--------------------------------------------------------------------------
2026-08-16 reconciliation gate
--------------------------------------------------------------------------
A single real controlled production validation (see
``docs/engineering/MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md``) sent the
certified request header (``X-Metric-Units: true``) and observed exactly one
provider rollup whose parsed ``vehicle.metric_units`` did NOT equal ``True``.
That single observation contradicts Polaris's prior assumption that the
returned Boolean must equal the requested Boolean. It does **not** tell us
what a returned ``False`` (or a returned ``None``) means -- imperial units,
an ignored header, a parser defect, and a provider documentation gap are all
still open possibilities, and this module must not guess among them.

The request-side policy below (what Polaris sends) remains certified and
unchanged: Polaris always requests ``X-Metric-Units: true`` / metric. What is
now explicitly **uncertified** is the relationship between that request and
the returned ``vehicle.metric_units`` Boolean. Until Motive explicitly
certifies that relationship, no returned unit indicator value -- ``True``,
``False``, or ``None`` -- makes a fuel-bearing rollup ready for durable
persistence. See ``validate_vehicle_utilization_unit_persistence_readiness``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Request-side policy (certified, unchanged). This is what Polaris sends.
# ---------------------------------------------------------------------------
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS = True
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE = "true"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM = "metric"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER = "X-Metric-Units"
MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED = False

# ---------------------------------------------------------------------------
# Returned-side policy (downgraded to unresolved by this gate). This is what
# Polaris currently knows -- and does not know -- about what Motive sends
# back.
# ---------------------------------------------------------------------------
MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS = "LIVE_PROVIDER_UNIT_INDICATOR_SEMANTICS_UNRESOLVED"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY = "X-Metric-Units = true"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUESTED_UNIT_SYSTEM = "metric"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY_CERTIFIED = True
MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED = False
MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN = False
MOTIVE_VEHICLE_UTILIZATION_DURABLE_FUEL_PERSISTENCE_ENABLED = False
MOTIVE_VEHICLE_UTILIZATION_COMBINE_FUEL_ACROSS_UNKNOWN_UNIT_CONTEXT = False

# Safe, neutral error codes. Neither implies a meaning for the returned value.
UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE = "provider_unit_indicator_semantics_unresolved"
UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE = "provider_unit_context_invalid_type"


@dataclass(frozen=True, slots=True)
class VehicleUtilizationUnitPersistenceReadiness:
    """Whether a returned rollup's unit context is ready for durable
    persistence.

    This is deliberately a *separate* concept from provider schema parse
    success (see ``app.connectors.motive_vehicle_utilization``). A rollup can
    parse successfully -- including preserving a returned ``True``,
    ``False``, or ``None`` ``metric_units`` value as observed context -- and
    still be ``ready_for_durable_persistence=False`` here, because Motive's
    returned-Boolean semantics are not yet certified.
    """

    ready_for_durable_persistence: bool
    error_code: str | None = None


def vehicle_utilization_writer_metric_units_header_value(metric_units: bool) -> str:
    """Return Motive's Boolean header spelling for an explicit unit mode.

    This is the certified *request*-side policy and is unaffected by the
    returned-side unit-indicator semantics being unresolved.
    """
    if type(metric_units) is not bool:
        raise ValueError("Motive utilization writer metric_units must be an explicit Boolean")
    return "true" if metric_units else "false"


def validate_vehicle_utilization_unit_persistence_readiness(
    returned_metric_units: Any,
) -> VehicleUtilizationUnitPersistenceReadiness:
    """Fail closed on durable persistence readiness for a returned rollup's
    unit context.

    This function makes NO claim about what a returned ``False`` or ``None``
    means. It only answers: "is this rollup's unit context certified enough
    to durably persist fuel-bearing metrics?" Today the answer is always
    "no" for every observed value -- ``True`` included -- because Motive's
    returned ``vehicle.metric_units`` Boolean semantics remain unresolved
    (``MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED``
    is ``False``). A malformed (non-Boolean, non-``None``) returned value is
    reported with a distinct, separate code, since that indicates a provider
    response shape problem rather than an open semantics question.

    A future gate may flip
    ``MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED``
    to ``True`` once Motive explicitly certifies the relationship between the
    requested and returned Boolean -- at which point this function would
    treat a returned ``True`` as ready. It must not be flipped by guessing.
    """
    if returned_metric_units is not None and type(returned_metric_units) is not bool:
        return VehicleUtilizationUnitPersistenceReadiness(
            ready_for_durable_persistence=False,
            error_code=UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE,
        )
    if not MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED:
        return VehicleUtilizationUnitPersistenceReadiness(
            ready_for_durable_persistence=False,
            error_code=UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE,
        )
    # Unreachable while semantics remain uncertified in this gate. Retained
    # so a future, explicitly-authorized certification gate has a defined
    # place to encode the certified relationship rather than needing to
    # redesign this function from scratch.
    if returned_metric_units is True:
        return VehicleUtilizationUnitPersistenceReadiness(ready_for_durable_persistence=True)
    return VehicleUtilizationUnitPersistenceReadiness(
        ready_for_durable_persistence=False,
        error_code=UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE,
    )
