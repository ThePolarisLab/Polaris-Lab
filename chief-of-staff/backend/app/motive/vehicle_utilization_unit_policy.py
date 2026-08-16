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

--------------------------------------------------------------------------
2026-08-16 unit-semantics-certification gate (official documentation review)
--------------------------------------------------------------------------
A follow-up gate reviewed current official Motive developer documentation
(developer-docs.gomotive.com) specifically to try to resolve the question
left open above: does the ``X-Metric-Units`` request header control the
unit system of the returned ``idle_fuel``/``driving_fuel`` values
independent of the returned ``vehicle.metric_units`` field? See
``docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md`` for
the full sourced summary. The short version: no reconciling statement was
found. The endpoint's own field description for ``metric_units`` is
suggestively unit-system-framed ("Indicates whether metric units are used
(e.g., false for imperial units)"), which reads differently from the more
clearly preference/configuration-oriented description Motive uses for the
same-named field on an unrelated, generic vehicle-details endpoint
("Indicates if the vehicle uses metric units") -- but neither page states or
implies whether the header and the field correspond, conflict, or operate
independently for this endpoint. This gate does not change any validation
behavior; it formalizes three previously-conflated concepts with explicit
names (below) and keeps every existing readiness/status flag exactly as PR
#163 left it.
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

# ---------------------------------------------------------------------------
# 2026-08-16 unit-semantics-certification gate (section 6): explicit,
# separately-named concepts. Polaris's code and contracts must stop treating
# "what we asked for" and "what Motive echoed back about the vehicle" as
# necessarily the same thing. These names are documentation/status-shaping
# only -- see ``vehicle_utilization_unit_semantics_contract_block`` below for
# where they are surfaced, and
# ``validate_vehicle_utilization_unit_persistence_readiness`` above for the
# one function that actually gates persistence. Defining these names does
# NOT change readiness behavior and does NOT certify anything new.
#
#   requested_measurement_system
#       What Polaris asks Motive for via the X-Metric-Units request header.
#       Certified and unchanged: "metric".
#   vehicle_configured_metric_preference
#       Motive's returned ``vehicle.metric_units`` Boolean. The raw provider
#       field name does not itself prove what units the returned
#       idle_fuel/driving_fuel values use -- it may describe a vehicle
#       display/configuration preference rather than the measurement system
#       of this response's numeric values. See the module docstring above
#       and MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md.
#   response_measurement_system_certification
#       Whether Polaris has explicitly certified the actual unit system of a
#       response's idle_fuel/driving_fuel values. Currently UNRESOLVED.
# ---------------------------------------------------------------------------
MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM = "metric"
MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH = "vehicle.metric_units"
MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION = "UNRESOLVED"
MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS = (
    "developer-docs.gomotive.com utilization overview and v1 vehicle-utilization "
    "reference page (retrieved 2026-08-16): no sentence anywhere on the "
    "official reference page reconciles the X-Metric-Units request header "
    "with the returned vehicle.metric_units field for this endpoint. The "
    "field's own description is suggestively unit-system-framed but is not an "
    "explicit causation statement, and the page's worked example (a false "
    "metric_units value paired with fuel figures the field descriptions call "
    "liters) is consistent with more than one reading. See "
    "docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md for "
    "the full sourced summary."
)


def vehicle_utilization_unit_semantics_contract_block() -> dict[str, Any]:
    """Build the explicit request-vs-response unit-semantics status block.

    Purely presentational/documentation-shaping: every value here is derived
    from the same module-level policy constants used by
    ``validate_vehicle_utilization_unit_persistence_readiness``. This
    function introduces no new certification decision -- it exists so that
    ``app.motive.vehicle_utilization_writer_contract`` (and any future
    caller) can expose the section-6 conceptual distinctions under clear,
    separately-named fields instead of one ambiguous ``metric_units`` flag.
    """
    return {
        "request_header": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER,
        "request_header_value": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
        "requested_measurement_system": MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM,
        "request_policy_certified": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY_CERTIFIED,
        "returned_vehicle_metric_units_semantics": {
            "field_path": MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH,
            "classification": "VEHICLE_CONFIGURED_METRIC_PREFERENCE_NOT_CERTIFIED_AS_RESPONSE_UNIT_PROOF",
            "equality_with_request_required": MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN,
        },
        "response_measurement_system": {
            "classification": MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION,
            "basis": MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS,
        },
        "durable_fuel_persistence_ready": MOTIVE_VEHICLE_UTILIZATION_DURABLE_FUEL_PERSISTENCE_ENABLED,
    }


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
