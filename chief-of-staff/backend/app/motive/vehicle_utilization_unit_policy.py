"""Canonical unit policy for Motive vehicle-utilization requests/writes.

The current verifier and bounded-evidence probes may still use their existing
environment-controlled request boundary. Durable writer enablement must use the
fixed Polaris-owned policy below instead.

--------------------------------------------------------------------------
2026-08-16 reconciliation gate (superseded below)
--------------------------------------------------------------------------
A single real controlled production validation (see
``docs/engineering/MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md``) sent the
certified request header (``X-Metric-Units: true``) and observed exactly one
provider rollup whose parsed ``vehicle.metric_units`` did NOT equal ``True``.
That single observation contradicted Polaris's prior assumption that the
returned Boolean must equal the requested Boolean, and this module was
downgraded to treat every returned value -- ``True`` included -- as
unresolved.

--------------------------------------------------------------------------
2026-08-16 unit-semantics-certification gate (superseded below)
--------------------------------------------------------------------------
A follow-up gate reviewed official Motive developer documentation
(developer-docs.gomotive.com) and found no statement reconciling the
``X-Metric-Units`` request header with the returned ``vehicle.metric_units``
field for this endpoint. No behavior changed; the module only formalized
explicit names for "what we asked for" vs. "what Motive echoed back."

--------------------------------------------------------------------------
2026-08-17 provider-confirmation gate (current)
--------------------------------------------------------------------------
Motive API Support sent a written reply on 2026-08-17 that directly answers
the open question above for ``GET /v1/vehicle_utilization``:

- ``X-Metric-Units=true`` requests metric measurement; ``idle_fuel`` and
  ``driving_fuel`` are therefore liters.
- ``X-Metric-Units=false`` requests imperial measurement; ``idle_fuel`` and
  ``driving_fuel`` are therefore gallons.
- the returned ``vehicle.metric_units`` field is a unit INDICATOR:
  ``true`` means metric, ``false`` means imperial.
- ``X-Metric-Units=true`` together with a returned ``vehicle.metric_units =
  false`` is NOT an expected/documented combination. When the requested unit
  system and the returned indicator disagree, integrations must fail closed
  and must not persist fuel values.
- ``idle_time``/``driving_time`` are seconds regardless of
  ``X-Metric-Units``.

This is a genuine upgrade, not a guess: it is sourced directly from Motive's
own written confirmation, not inferred from the single prior live
observation or from official-docs phrasing. This module now certifies the
returned-indicator MEANING and the request/response consistency rule, while
remaining strictly fail-closed whenever the requested and returned unit
context disagree, is missing, or is malformed. No unit CONVERSION is ever
performed, and no fuel value is ever persisted across an unresolved or
mismatched unit context.

--------------------------------------------------------------------------
2026-08-17 account-default unit-request-mode audit gate (current)
--------------------------------------------------------------------------
A separate, working local Motive Fuel/IFTA integration on the same Motive
account (NOT part of this repo -- see
``docs/engineering/MOTIVE_UTILIZATION_ACCOUNT_DEFAULT_UNIT_MODE.md`` for the
full writeup) authenticates with the same certified ``X-API-Key`` pattern,
never sends an ``X-Metric-Units`` header at all for ``/v1/fuel_purchases`` or
``/v1/ifta/summary``, and simply trusts whatever unit the provider returns.
That is supporting evidence for a plausible *account-default* request mode
for ``/v1/vehicle_utilization`` -- it is NOT proof that this endpoint behaves
the same way as those other endpoints.

Prior to this gate, "what Polaris requested" was represented everywhere as a
plain ``bool`` (``requested_metric_units``). A ``bool`` cannot represent a
third state -- "no X-Metric-Units header was sent at all" -- so this gate
introduces an explicit three-value representation,
:class:`MotiveVehicleUtilizationUnitRequestMode`, alongside the existing
Boolean-based API rather than replacing it:

- ``METRIC``: send ``X-Metric-Units: true``; a returned
  ``vehicle.metric_units`` of anything other than ``True`` is a
  provider-confirmed mismatch and fails closed, exactly as the existing
  canonical (``requested_metric_units=True``) behavior always has.
- ``IMPERIAL``: send ``X-Metric-Units: false``; symmetric to ``METRIC`` with
  the Boolean flipped. Not used by any real caller yet.
- ``ACCOUNT_DEFAULT``: omit ``X-Metric-Units`` entirely. No unit system is
  forced, so no mismatch is possible: a returned ``True`` or ``False`` is
  ready for durable persistence exactly as returned (``True`` => metric,
  ``False`` => imperial). A missing (``None``) or malformed returned
  indicator still fails closed -- account-default trusts the returned
  Boolean, never a guess.

Every existing caller that only ever passes the plain ``bool``
``requested_metric_units`` parameter is completely unaffected: the new
``requested_mode`` parameter defaults to ``None``, in which case this module
derives the mode from the legacy Boolean and reproduces the exact prior
behavior, including the exact prior error codes.

2026-08-17 controlled-route validation gate (current): the bounded controlled
vehicle-utilization write validation route
(``app/motive/vehicle_utilization_controlled_write.py``) now explicitly opts
into ``MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`` for its one
provider request and its one writer transaction call -- it no longer forces
the canonical ``X-Metric-Units: true`` header. This is still NOT a live proof
of ``/v1/vehicle_utilization`` account-default behavior: no account-default
request against this endpoint has ever actually been made (the controlled
write route's feature flag,
``MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED``, remains disabled by
default and no live call has been made under this change). See the
account-default engineering doc for the explicit scope decision and the
still-pending live-staging proof step.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Request-side policy (certified, unchanged). This is what Polaris sends.
# ---------------------------------------------------------------------------
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS = True
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE = "true"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM = "metric"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER = "X-Metric-Units"
MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED = False

# Provider-confirmed (2026-08-17) fuel-unit mapping. idle_time/driving_time
# are always seconds, independent of X-Metric-Units.
MOTIVE_VEHICLE_UTILIZATION_METRIC_FUEL_UNIT = "liters"
MOTIVE_VEHICLE_UTILIZATION_IMPERIAL_FUEL_UNIT = "gallons"
MOTIVE_VEHICLE_UTILIZATION_TIME_UNIT = "seconds"

# ---------------------------------------------------------------------------
# Returned-side policy. 2026-08-17 provider written confirmation upgrades
# this from unresolved to defined-but-fail-closed-on-mismatch semantics.
# ---------------------------------------------------------------------------
MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS = "PROVIDER_CONFIRMED_FAIL_CLOSED_ON_MISMATCH"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY = "X-Metric-Units = true"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUESTED_UNIT_SYSTEM = "metric"
MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY_CERTIFIED = True
MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED = True
MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN = True
# A fuel-bearing rollup CAN now become unit-ready when the requested and
# returned unit context are both present and agree (see
# validate_vehicle_utilization_unit_persistence_readiness). This flag is
# purely descriptive/status metadata -- it does not itself gate any runtime
# behavior. Independently-gated feature flags (the controlled write route's
# MOTIVE_VEHICLE_UTILIZATION_CONTROLLED_WRITE_ENABLED, checkpoint
# advancement, and scheduled ingestion) remain OFF and are unaffected by
# this flag.
MOTIVE_VEHICLE_UTILIZATION_DURABLE_FUEL_PERSISTENCE_ENABLED = True
MOTIVE_VEHICLE_UTILIZATION_COMBINE_FUEL_ACROSS_UNKNOWN_UNIT_CONTEXT = False

# Safe, neutral error codes.
# - missing (None) returned indicator: unresolved, we have no data to compare.
# - non-Boolean, non-None returned indicator: a provider response-shape
#   problem, not a semantics question.
# - present Boolean that disagrees with the requested Boolean: a
#   provider-confirmed, definitively-known mismatch.
UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE = "provider_unit_indicator_semantics_unresolved"
UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE = "provider_unit_context_invalid_type"
UNIT_CONTEXT_MISMATCH_ERROR_CODE = "provider_unit_policy_mismatch"

# ---------------------------------------------------------------------------
# Explicit, separately-named concepts (section 6 of the 2026-08-16
# unit-semantics-certification gate, now provider-confirmed rather than
# aspirational).
#
#   requested_measurement_system
#       What Polaris asks Motive for via the X-Metric-Units request header.
#       Certified and unchanged: "metric".
#   vehicle_configured_metric_preference / provider unit indicator
#       Motive's returned ``vehicle.metric_units`` Boolean. Now
#       provider-confirmed: True means metric, False means imperial.
#   response_measurement_system_certification
#       Whether Polaris has explicitly certified the actual unit system of a
#       response's idle_fuel/driving_fuel values. Now
#       PROVIDER_CONFIRMED_FAIL_CLOSED_ON_MISMATCH: certified when the
#       requested and returned unit context agree; any disagreement, any
#       missing returned indicator, or any malformed returned value fails
#       closed rather than being resolved by inference.
# ---------------------------------------------------------------------------
MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM = "metric"
MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH = "vehicle.metric_units"
MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION = "PROVIDER_CONFIRMED_FAIL_CLOSED_ON_MISMATCH"
# ---------------------------------------------------------------------------
# 2026-08-17 account-default unit-request-mode audit gate: explicit 3-value
# request-mode representation. See the module docstring above for the full
# rationale. This is additive; every function below that predates this gate
# keeps its exact prior ``bool``-based signature and behavior.
# ---------------------------------------------------------------------------


class MotiveVehicleUtilizationUnitRequestMode(str, Enum):
    """The three explicit request modes Polaris may use for
    ``GET /v1/vehicle_utilization``.

    A plain ``bool`` can only ever represent ``METRIC``/``IMPERIAL`` -- it
    structurally cannot represent "no X-Metric-Units header was sent at
    all". This enum exists so ``ACCOUNT_DEFAULT`` is a first-class, named
    state rather than an overload of the existing Boolean semantics.
    """

    METRIC = "metric"
    IMPERIAL = "imperial"
    ACCOUNT_DEFAULT = "account_default"


MOTIVE_VEHICLE_UTILIZATION_UNIT_REQUEST_MODE_ACCOUNT_DEFAULT_BASIS = (
    "A separate, working local Motive Fuel/IFTA integration on the same "
    "Motive account authenticates with the same certified X-API-Key "
    "pattern and never sends an X-Metric-Units header for /v1/fuel_purchases "
    "or /v1/ifta/summary, trusting whatever unit the provider returns. This "
    "motivates offering an account-default request mode for "
    "/v1/vehicle_utilization but does NOT certify that this endpoint's "
    "account-default behavior matches those other endpoints -- no "
    "account-default vehicle_utilization request has ever been made live."
)


def vehicle_utilization_unit_request_mode_from_bool(requested_metric_units: bool) -> "MotiveVehicleUtilizationUnitRequestMode":
    """Map the legacy explicit-Boolean request policy onto the new 3-mode enum."""
    if type(requested_metric_units) is not bool:
        raise ValueError("Motive utilization requested_metric_units must be an explicit Boolean")
    return (
        MotiveVehicleUtilizationUnitRequestMode.METRIC
        if requested_metric_units
        else MotiveVehicleUtilizationUnitRequestMode.IMPERIAL
    )


def vehicle_utilization_unit_request_mode_header_value(mode: "MotiveVehicleUtilizationUnitRequestMode") -> str | None:
    """Return the exact ``X-Metric-Units`` header value for ``mode``.

    Returns ``None`` for :attr:`MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT`
    -- callers must interpret ``None`` as "omit the header entirely", never as
    an empty-string header value.
    """
    if not isinstance(mode, MotiveVehicleUtilizationUnitRequestMode):
        raise ValueError("Motive utilization unit request mode must be an explicit MotiveVehicleUtilizationUnitRequestMode")
    if mode is MotiveVehicleUtilizationUnitRequestMode.METRIC:
        return MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE
    if mode is MotiveVehicleUtilizationUnitRequestMode.IMPERIAL:
        return "false"
    return None


def vehicle_utilization_unit_request_mode_measurement_system(mode: "MotiveVehicleUtilizationUnitRequestMode") -> str | None:
    """The measurement system Polaris is explicitly requesting, or ``None``
    when ``ACCOUNT_DEFAULT`` means no measurement system is being forced --
    the actual system is only known once the response is observed."""
    if not isinstance(mode, MotiveVehicleUtilizationUnitRequestMode):
        raise ValueError("Motive utilization unit request mode must be an explicit MotiveVehicleUtilizationUnitRequestMode")
    if mode is MotiveVehicleUtilizationUnitRequestMode.METRIC:
        return "metric"
    if mode is MotiveVehicleUtilizationUnitRequestMode.IMPERIAL:
        return "imperial"
    return None


def vehicle_utilization_unit_request_mode_expected_fuel_unit(mode: "MotiveVehicleUtilizationUnitRequestMode") -> str | None:
    """The fuel unit Polaris expects for a forced mode, or ``None`` for
    ``ACCOUNT_DEFAULT`` -- do not invent an expected fuel unit before the
    provider responds; see :func:`vehicle_utilization_provider_unit_indicator`
    for the returned-side mapping instead."""
    if not isinstance(mode, MotiveVehicleUtilizationUnitRequestMode):
        raise ValueError("Motive utilization unit request mode must be an explicit MotiveVehicleUtilizationUnitRequestMode")
    if mode is MotiveVehicleUtilizationUnitRequestMode.METRIC:
        return MOTIVE_VEHICLE_UTILIZATION_METRIC_FUEL_UNIT
    if mode is MotiveVehicleUtilizationUnitRequestMode.IMPERIAL:
        return MOTIVE_VEHICLE_UTILIZATION_IMPERIAL_FUEL_UNIT
    return None
MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS = (
    "Motive API Support written reply (2026-08-17) confirmed GET "
    "/v1/vehicle_utilization unit semantics directly: X-Metric-Units=true "
    "requests metric measurement (idle_fuel/driving_fuel in liters); "
    "X-Metric-Units=false requests imperial measurement (idle_fuel/driving_fuel "
    "in gallons); the returned vehicle.metric_units indicator means "
    "true=metric and false=imperial; idle_time/driving_time are always "
    "seconds regardless of X-Metric-Units; and X-Metric-Units=true together "
    "with a returned vehicle.metric_units=false is not an expected/documented "
    "combination -- Motive Support directed integrations to fail closed and "
    "not persist fuel values whenever the requested and returned unit context "
    "disagree. This supersedes the prior UNRESOLVED classification recorded "
    "in docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md."
)


def vehicle_utilization_requested_measurement_system(requested_metric_units: bool) -> str:
    """Provider-confirmed mapping of the request header to a measurement system."""
    if type(requested_metric_units) is not bool:
        raise ValueError("Motive utilization requested_metric_units must be an explicit Boolean")
    return "metric" if requested_metric_units else "imperial"


def vehicle_utilization_requested_fuel_unit(requested_metric_units: bool) -> str:
    """Provider-confirmed fuel unit for idle_fuel/driving_fuel given the request header."""
    if type(requested_metric_units) is not bool:
        raise ValueError("Motive utilization requested_metric_units must be an explicit Boolean")
    return (
        MOTIVE_VEHICLE_UTILIZATION_METRIC_FUEL_UNIT
        if requested_metric_units
        else MOTIVE_VEHICLE_UTILIZATION_IMPERIAL_FUEL_UNIT
    )


def vehicle_utilization_provider_unit_indicator(returned_metric_units: Any) -> str | None:
    """Provider-confirmed meaning of the returned ``vehicle.metric_units`` Boolean.

    Returns ``"metric"`` for ``True``, ``"imperial"`` for ``False``, and
    ``None`` when the value is missing or malformed -- callers must never
    guess a measurement system in that case.
    """
    if returned_metric_units is True:
        return "metric"
    if returned_metric_units is False:
        return "imperial"
    return None


def vehicle_utilization_unit_context_consistent(requested_metric_units: bool, returned_metric_units: Any) -> bool:
    """Section 9 consistency rule: does the returned indicator agree with the request?

    ``True`` only when both sides are explicit, equal Booleans (true/true or
    false/false). A missing (``None``) or malformed returned value is never
    "consistent" -- those are distinct, separately-coded failures handled by
    :func:`validate_vehicle_utilization_unit_persistence_readiness`.
    """
    if type(requested_metric_units) is not bool:
        raise ValueError("Motive utilization requested_metric_units must be an explicit Boolean")
    if type(returned_metric_units) is not bool:
        return False
    return requested_metric_units is returned_metric_units


def vehicle_utilization_unit_semantics_contract_block() -> dict[str, Any]:
    """Build the explicit request-vs-response unit-semantics status block.

    Every value here is derived from the same module-level policy constants
    used by :func:`validate_vehicle_utilization_unit_persistence_readiness`.
    """
    return {
        "request_header": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER,
        "request_header_value": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
        "requested_measurement_system": MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM,
        "request_policy_certified": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY_CERTIFIED,
        "canonical_requested_fuel_unit": MOTIVE_VEHICLE_UTILIZATION_METRIC_FUEL_UNIT,
        "returned_vehicle_metric_units_semantics": {
            "field_path": MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH,
            "classification": "PROVIDER_CONFIRMED_UNIT_INDICATOR",
            "true_means": "metric",
            "false_means": "imperial",
            "equality_with_request_required": MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN,
        },
        "response_measurement_system": {
            "classification": MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION,
            "basis": MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS,
        },
        "time_unit": MOTIVE_VEHICLE_UTILIZATION_TIME_UNIT,
        "mismatch_error_code": UNIT_CONTEXT_MISMATCH_ERROR_CODE,
        "missing_indicator_error_code": UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE,
        "invalid_type_error_code": UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE,
        "unit_conversion_enabled": MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
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
    still be ``ready_for_durable_persistence=False`` here, because the
    requested and returned unit context disagree, is missing, or is
    malformed.
    """

    ready_for_durable_persistence: bool
    error_code: str | None = None
    resolved_metric_units: bool | None = None
    """The unit-context Boolean a caller should persist when ready.

    Always equal to the (already-validated) returned value when
    ``ready_for_durable_persistence`` is ``True``: for a forced mode
    (``METRIC``/``IMPERIAL``) this is necessarily the same as the certified
    requested Boolean, since readiness requires them to agree; for
    ``ACCOUNT_DEFAULT`` it is whichever Boolean the provider actually
    returned (no unit system was forced, so both ``True`` and ``False`` can
    be ready). ``None`` whenever ``ready_for_durable_persistence`` is
    ``False`` -- never a value to persist."""


def vehicle_utilization_writer_metric_units_header_value(metric_units: bool) -> str:
    """Return Motive's Boolean header spelling for an explicit unit mode."""
    if type(metric_units) is not bool:
        raise ValueError("Motive utilization writer metric_units must be an explicit Boolean")
    return "true" if metric_units else "false"


def validate_vehicle_utilization_unit_persistence_readiness(
    returned_metric_units: Any,
    *,
    requested_metric_units: bool = MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
    requested_mode: "MotiveVehicleUtilizationUnitRequestMode | None" = None,
) -> VehicleUtilizationUnitPersistenceReadiness:
    """Fail-closed durable-persistence readiness gate.

    2026-08-17 provider-confirmed semantics for the two FORCED modes
    (``METRIC``/``IMPERIAL``, i.e. an explicit ``X-Metric-Units`` header was
    sent):

    - requested METRIC (``True``), returned ``True`` -> ready (metric).
    - requested IMPERIAL (``False``), returned ``False`` -> ready (imperial).
    - requested METRIC, returned ``False`` (or requested IMPERIAL, returned
      ``True``) -> fail closed with :data:`UNIT_CONTEXT_MISMATCH_ERROR_CODE`
      (``provider_unit_policy_mismatch``). Motive Support confirmed the
      true-request/false-response combination is not expected/documented and
      directed integrations to fail closed rather than persist; the same
      fail-closed treatment applies symmetrically to false-request/
      true-response.
    - ``returned=None`` -> fail closed with
      :data:`UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE`: Polaris has no
      returned indicator to compare against the request.
    - a non-Boolean, non-``None`` returned value -> fail closed with
      :data:`UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE`: a provider response-shape
      problem, not an open semantics question.

    2026-08-17 account-default unit-request-mode audit gate semantics for
    ``requested_mode=MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT``
    (i.e. no ``X-Metric-Units`` header was sent at all): no unit system was
    forced, so a returned ``True`` or ``False`` is ALWAYS ready -- there is no
    mismatch to fail closed on, because Polaris made no request-side claim to
    disagree with. The returned Boolean becomes the observed unit context
    (``True`` => metric, ``False`` => imperial) and is reported back via
    ``resolved_metric_units``. A missing (``None``) or malformed returned
    indicator still fails closed exactly as it does for the forced modes --
    account-default trusts only an explicit, well-formed returned Boolean,
    never a guess.

    ``requested_metric_units`` defaults to the certified canonical writer
    policy (always ``True``) so the real writer transaction -- which only
    ever requests the canonical policy -- can keep calling this function
    with a single positional argument. When ``requested_mode`` is omitted
    (``None``, the default), it is derived from ``requested_metric_units``
    via :func:`vehicle_utilization_unit_request_mode_from_bool`, which
    reproduces this function's exact prior (pre-account-default-gate)
    behavior and error codes for every existing caller. Passing
    ``requested_mode`` explicitly (e.g. ``ACCOUNT_DEFAULT``) takes
    precedence over ``requested_metric_units``.

    If :data:`MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED`
    were ever reverted to ``False`` (a kill switch, not expected in normal
    operation), every returned value -- including an otherwise-consistent
    match, and including every ``ACCOUNT_DEFAULT`` value -- fails closed with
    the neutral unresolved code, never guessing a certification that has
    been explicitly withdrawn.
    """
    if requested_mode is not None and not isinstance(requested_mode, MotiveVehicleUtilizationUnitRequestMode):
        raise ValueError("Motive utilization requested_mode must be an explicit MotiveVehicleUtilizationUnitRequestMode")
    if requested_mode is None:
        resolved_mode = vehicle_utilization_unit_request_mode_from_bool(requested_metric_units)
    else:
        resolved_mode = requested_mode

    if returned_metric_units is not None and type(returned_metric_units) is not bool:
        return VehicleUtilizationUnitPersistenceReadiness(
            ready_for_durable_persistence=False,
            error_code=UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE,
        )
    if returned_metric_units is None:
        return VehicleUtilizationUnitPersistenceReadiness(
            ready_for_durable_persistence=False,
            error_code=UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE,
        )
    if not MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED:
        return VehicleUtilizationUnitPersistenceReadiness(
            ready_for_durable_persistence=False,
            error_code=UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE,
        )

    if resolved_mode is MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT:
        # No unit system was forced -- both True and False are ready, and
        # the returned Boolean IS the observed unit context.
        return VehicleUtilizationUnitPersistenceReadiness(
            ready_for_durable_persistence=True,
            resolved_metric_units=returned_metric_units,
        )

    expected_returned = resolved_mode is MotiveVehicleUtilizationUnitRequestMode.METRIC
    if expected_returned is not returned_metric_units:
        return VehicleUtilizationUnitPersistenceReadiness(
            ready_for_durable_persistence=False,
            error_code=UNIT_CONTEXT_MISMATCH_ERROR_CODE,
        )
    return VehicleUtilizationUnitPersistenceReadiness(
        ready_for_durable_persistence=True,
        resolved_metric_units=returned_metric_units,
    )
