from __future__ import annotations

import os

import pytest

from app.motive.vehicle_utilization_unit_policy import (
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY_CERTIFIED,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUESTED_UNIT_SYSTEM,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM,
    MOTIVE_VEHICLE_UTILIZATION_COMBINE_FUEL_ACROSS_UNKNOWN_UNIT_CONTEXT,
    MOTIVE_VEHICLE_UTILIZATION_DURABLE_FUEL_PERSISTENCE_ENABLED,
    MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM,
    MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS,
    MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION,
    MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED,
    MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS,
    MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH,
    validate_vehicle_utilization_unit_persistence_readiness,
    vehicle_utilization_unit_semantics_contract_block,
    vehicle_utilization_writer_metric_units_header_value,
)


# ---------------------------------------------------------------------------
# Request-side policy: certified and unchanged by this gate.
# ---------------------------------------------------------------------------
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


def test_request_side_canonical_policy_is_still_the_certified_request_header() -> None:
    """The request Polaris sends is not in question -- only what Motive
    returns is unresolved. Do not remove the explicit metric request header.
    """
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY == "X-Metric-Units = true"
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUESTED_UNIT_SYSTEM == "metric"
    assert MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY_CERTIFIED is True


# ---------------------------------------------------------------------------
# 2026-08-16 reconciliation gate: downgraded, unresolved returned-side policy.
# ---------------------------------------------------------------------------
def test_unit_policy_status_is_downgraded_to_unresolved() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS == "LIVE_PROVIDER_UNIT_INDICATOR_SEMANTICS_UNRESOLVED"
    assert MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED is False
    assert MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN is False
    assert MOTIVE_VEHICLE_UTILIZATION_DURABLE_FUEL_PERSISTENCE_ENABLED is False
    assert MOTIVE_VEHICLE_UTILIZATION_COMBINE_FUEL_ACROSS_UNKNOWN_UNIT_CONTEXT is False


# ---------------------------------------------------------------------------
# Persistence-readiness validator: the redesigned gate.
#
# CRITICAL: none of these tests may assert or imply what a returned False or
# None *means*. They only prove that no returned value currently makes a
# rollup ready for durable persistence, and that a malformed (non-Boolean,
# non-None) value is reported with a distinct, separate code.
# ---------------------------------------------------------------------------
def test_returned_true_does_not_automatically_certify_persistence_readiness() -> None:
    """A returned True must never be treated as automatically certified --
    certification requires an explicit, separate policy flag, not merely
    observing the same Boolean Polaris requested.
    """
    result = validate_vehicle_utilization_unit_persistence_readiness(True)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == "provider_unit_indicator_semantics_unresolved"


def test_returned_false_is_not_interpreted_as_imperial() -> None:
    """A returned False must never be interpreted as imperial, as a signal
    that the header was ignored, or as any other specific claim -- it is
    only unresolved, using the exact same neutral code as True and None.
    """
    result = validate_vehicle_utilization_unit_persistence_readiness(False)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == "provider_unit_indicator_semantics_unresolved"


def test_returned_none_remains_unresolved() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(None)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == "provider_unit_indicator_semantics_unresolved"


def test_true_false_and_none_all_share_the_same_neutral_unresolved_code() -> None:
    """No returned value is treated as more or less suspicious than another
    -- they all fail the same way, for the same stated reason (semantics
    unresolved), never a value-specific reason.
    """
    codes = {
        validate_vehicle_utilization_unit_persistence_readiness(True).error_code,
        validate_vehicle_utilization_unit_persistence_readiness(False).error_code,
        validate_vehicle_utilization_unit_persistence_readiness(None).error_code,
    }
    assert codes == {"provider_unit_indicator_semantics_unresolved"}


@pytest.mark.parametrize("returned_metric_units", ["true", "false", 1, 0, "metric", "imperial", []])
def test_malformed_returned_type_fails_closed_with_a_distinct_code(returned_metric_units: object) -> None:
    """A non-Boolean, non-None returned value is a provider response-shape
    problem, not an open semantics question, so it gets its own separate
    code rather than being folded into the neutral unresolved code.
    """
    result = validate_vehicle_utilization_unit_persistence_readiness(returned_metric_units)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == "provider_unit_context_invalid_type"


def test_persistence_readiness_gate_can_become_certified_in_a_future_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit representation, not guesswork: flipping the module-level
    certified flag (only appropriate in a future, separately-authorized
    gate once Motive explicitly certifies the relationship) is the only way
    a returned True becomes ready. This proves the gate is not hard-coded
    to permanently reject True -- it is conditioned on an explicit policy
    flag rather than the value itself.
    """
    import app.motive.vehicle_utilization_unit_policy as unit_policy

    monkeypatch.setattr(unit_policy, "MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED", True)

    true_result = unit_policy.validate_vehicle_utilization_unit_persistence_readiness(True)
    false_result = unit_policy.validate_vehicle_utilization_unit_persistence_readiness(False)

    assert true_result.ready_for_durable_persistence is True
    assert false_result.ready_for_durable_persistence is False
    assert false_result.error_code == "provider_unit_indicator_semantics_unresolved"


# ---------------------------------------------------------------------------
# 2026-08-16 unit-semantics-certification gate: section 6 conceptual naming.
#
# These tests prove the new documentation-driven conceptual distinctions
# exist and are wired into the contract block -- they must NOT assert or
# imply what a returned False/True/None value means, and they must NOT
# change any persistence-readiness outcome (that is covered above).
# ---------------------------------------------------------------------------
def test_requested_measurement_system_is_named_and_metric() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM == "metric"


def test_response_measurement_system_certification_is_unresolved_with_a_cited_basis() -> None:
    """Outcome B: no official documentation reconciles the request header
    with the returned vehicle.metric_units field for this endpoint, so the
    response measurement system stays UNRESOLVED with a documented basis
    (not a guess, not silence).
    """
    assert MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION == "UNRESOLVED"
    assert isinstance(MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS, str)
    assert len(MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS) > 0
    assert "developer-docs.gomotive.com" in MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS


def test_vehicle_configured_metric_preference_field_path_is_named() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH == "vehicle.metric_units"


def test_unit_semantics_contract_block_shape() -> None:
    """Proves the section-18 unit_semantics block's exact shape and that it
    is entirely derived from the existing certified/uncertified policy
    constants -- no new certification decision is smuggled in here.
    """
    block = vehicle_utilization_unit_semantics_contract_block()

    assert block["request_header"] == MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER
    assert block["request_header_value"] is True
    assert block["requested_measurement_system"] == "metric"
    assert block["request_policy_certified"] is True

    returned = block["returned_vehicle_metric_units_semantics"]
    assert returned["field_path"] == "vehicle.metric_units"
    assert returned["equality_with_request_required"] is False

    response = block["response_measurement_system"]
    assert response["classification"] == "UNRESOLVED"
    assert isinstance(response["basis"], str) and response["basis"]

    assert block["durable_fuel_persistence_ready"] is False


def test_unit_semantics_contract_block_never_asserts_false_means_imperial() -> None:
    """No word in the block's textual content may claim a returned False (or
    True) has a specific meaning -- only that the relationship is unresolved.
    """
    block = vehicle_utilization_unit_semantics_contract_block()
    rendered = " ".join(
        str(value)
        for value in (
            block["returned_vehicle_metric_units_semantics"]["classification"],
            block["response_measurement_system"]["classification"],
            block["response_measurement_system"]["basis"],
        )
    ).lower()

    assert "false means imperial" not in rendered
    assert "false implies imperial" not in rendered
    assert "certified_metric" not in rendered
