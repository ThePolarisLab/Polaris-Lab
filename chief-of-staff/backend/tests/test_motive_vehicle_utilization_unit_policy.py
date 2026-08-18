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
    MOTIVE_VEHICLE_UTILIZATION_IMPERIAL_FUEL_UNIT,
    MOTIVE_VEHICLE_UTILIZATION_METRIC_FUEL_UNIT,
    MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM,
    MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS,
    MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION,
    MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED,
    MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN,
    MOTIVE_VEHICLE_UTILIZATION_TIME_UNIT,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS,
    MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH,
    UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE,
    UNIT_CONTEXT_MISMATCH_ERROR_CODE,
    UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE,
    MotiveVehicleUtilizationUnitRequestMode,
    validate_vehicle_utilization_unit_persistence_readiness,
    vehicle_utilization_provider_unit_indicator,
    vehicle_utilization_requested_fuel_unit,
    vehicle_utilization_requested_measurement_system,
    vehicle_utilization_unit_context_consistent,
    vehicle_utilization_unit_request_mode_expected_fuel_unit,
    vehicle_utilization_unit_request_mode_from_bool,
    vehicle_utilization_unit_request_mode_header_value,
    vehicle_utilization_unit_request_mode_measurement_system,
    vehicle_utilization_unit_semantics_contract_block,
    vehicle_utilization_writer_metric_units_header_value,
)

METRIC = MotiveVehicleUtilizationUnitRequestMode.METRIC
IMPERIAL = MotiveVehicleUtilizationUnitRequestMode.IMPERIAL
ACCOUNT_DEFAULT = MotiveVehicleUtilizationUnitRequestMode.ACCOUNT_DEFAULT


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
# 2026-08-17 provider-confirmation gate: upgraded, defined,
# fail-closed-on-mismatch returned-side policy.
# ---------------------------------------------------------------------------
def test_unit_policy_status_is_upgraded_to_provider_confirmed() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS == "PROVIDER_CONFIRMED_FAIL_CLOSED_ON_MISMATCH"
    assert MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED is True
    assert MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN is True
    assert MOTIVE_VEHICLE_UTILIZATION_DURABLE_FUEL_PERSISTENCE_ENABLED is True
    assert MOTIVE_VEHICLE_UTILIZATION_COMBINE_FUEL_ACROSS_UNKNOWN_UNIT_CONTEXT is False


def test_fuel_and_time_unit_mapping_is_provider_confirmed() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_METRIC_FUEL_UNIT == "liters"
    assert MOTIVE_VEHICLE_UTILIZATION_IMPERIAL_FUEL_UNIT == "gallons"
    assert MOTIVE_VEHICLE_UTILIZATION_TIME_UNIT == "seconds"
    assert vehicle_utilization_requested_fuel_unit(True) == "liters"
    assert vehicle_utilization_requested_fuel_unit(False) == "gallons"
    assert vehicle_utilization_requested_measurement_system(True) == "metric"
    assert vehicle_utilization_requested_measurement_system(False) == "imperial"


@pytest.mark.parametrize("value", [1, 0, "true", "metric", None, []])
def test_requested_measurement_system_helpers_reject_non_boolean(value: object) -> None:
    with pytest.raises(ValueError, match="explicit Boolean"):
        vehicle_utilization_requested_measurement_system(value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="explicit Boolean"):
        vehicle_utilization_requested_fuel_unit(value)  # type: ignore[arg-type]


def test_provider_unit_indicator_mapping() -> None:
    assert vehicle_utilization_provider_unit_indicator(True) == "metric"
    assert vehicle_utilization_provider_unit_indicator(False) == "imperial"
    assert vehicle_utilization_provider_unit_indicator(None) is None


@pytest.mark.parametrize("value", ["true", "false", 1, 0, "metric", []])
def test_provider_unit_indicator_mapping_returns_none_for_malformed_values(value: object) -> None:
    assert vehicle_utilization_provider_unit_indicator(value) is None


# ---------------------------------------------------------------------------
# Section 9: request/response consistency rule.
# ---------------------------------------------------------------------------
def test_true_true_is_consistent() -> None:
    assert vehicle_utilization_unit_context_consistent(True, True) is True


def test_false_false_is_consistent() -> None:
    assert vehicle_utilization_unit_context_consistent(False, False) is True


def test_true_false_is_not_consistent() -> None:
    assert vehicle_utilization_unit_context_consistent(True, False) is False


def test_false_true_is_not_consistent() -> None:
    assert vehicle_utilization_unit_context_consistent(False, True) is False


@pytest.mark.parametrize("returned_metric_units", [None, "true", 1, 0, []])
def test_missing_or_malformed_returned_value_is_never_consistent(returned_metric_units: object) -> None:
    assert vehicle_utilization_unit_context_consistent(True, returned_metric_units) is False
    assert vehicle_utilization_unit_context_consistent(False, returned_metric_units) is False


def test_consistency_helper_requires_an_explicit_requested_boolean() -> None:
    with pytest.raises(ValueError, match="explicit Boolean"):
        vehicle_utilization_unit_context_consistent(1, True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Persistence-readiness validator: provider-confirmed, fail-closed-on-mismatch.
# ---------------------------------------------------------------------------
def test_canonical_writer_true_true_is_ready_for_durable_persistence() -> None:
    """The canonical writer always requests True; a returned True now agrees
    with the request and is unit-ready (other writer conditions still apply
    separately)."""
    result = validate_vehicle_utilization_unit_persistence_readiness(True)

    assert result.ready_for_durable_persistence is True
    assert result.error_code is None


def test_canonical_writer_true_request_with_false_returned_is_a_provider_confirmed_mismatch() -> None:
    """A returned False against the canonical True request is exactly the
    combination Motive Support confirmed is not expected/documented -- it
    fails closed with the mismatch code, never interpreted as imperial."""
    result = validate_vehicle_utilization_unit_persistence_readiness(False)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_CONTEXT_MISMATCH_ERROR_CODE


def test_false_request_false_returned_is_ready_for_durable_persistence() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(False, requested_metric_units=False)

    assert result.ready_for_durable_persistence is True
    assert result.error_code is None


def test_false_request_true_returned_is_a_provider_confirmed_mismatch() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(True, requested_metric_units=False)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_CONTEXT_MISMATCH_ERROR_CODE


@pytest.mark.parametrize("requested_metric_units", [True, False])
def test_returned_none_remains_unresolved_and_fails_closed(requested_metric_units: bool) -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(None, requested_metric_units=requested_metric_units)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE


@pytest.mark.parametrize("returned_metric_units", ["true", "false", 1, 0, "metric", "imperial", []])
def test_malformed_returned_type_fails_closed_with_a_distinct_code(returned_metric_units: object) -> None:
    """A non-Boolean, non-None returned value is a provider response-shape
    problem, not a semantics question, so it gets its own separate code."""
    result = validate_vehicle_utilization_unit_persistence_readiness(returned_metric_units)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE


def test_missing_and_malformed_never_get_the_mismatch_code() -> None:
    """The mismatch code is reserved for a present, well-formed, disagreeing
    Boolean -- never for a missing or malformed value."""
    codes = {
        validate_vehicle_utilization_unit_persistence_readiness(None).error_code,
        validate_vehicle_utilization_unit_persistence_readiness("not-a-bool").error_code,
    }
    assert UNIT_CONTEXT_MISMATCH_ERROR_CODE not in codes


def test_persistence_readiness_gate_can_be_reverted_by_the_certification_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """If MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED
    were ever reverted to False (a kill switch, not expected in normal
    operation), every returned value -- including an otherwise-consistent
    match -- fails closed with the neutral unresolved code rather than
    silently keeping the certification."""
    import app.motive.vehicle_utilization_unit_policy as unit_policy

    monkeypatch.setattr(unit_policy, "MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED", False)

    true_result = unit_policy.validate_vehicle_utilization_unit_persistence_readiness(True)
    false_result = unit_policy.validate_vehicle_utilization_unit_persistence_readiness(False)

    assert true_result.ready_for_durable_persistence is False
    assert true_result.error_code == UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE
    assert false_result.ready_for_durable_persistence is False
    assert false_result.error_code == UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE


# ---------------------------------------------------------------------------
# Section 6 conceptual naming, now provider-confirmed (2026-08-17 gate).
# ---------------------------------------------------------------------------
def test_requested_measurement_system_is_named_and_metric() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_REQUESTED_MEASUREMENT_SYSTEM == "metric"


def test_response_measurement_system_certification_is_provider_confirmed_with_a_cited_basis() -> None:
    """Motive API Support's 2026-08-17 written reply confirmed the
    request/response relationship for this endpoint, so the response
    measurement system upgrades from UNRESOLVED to a defined,
    fail-closed-on-mismatch classification with a documented basis (not a
    guess, not silence).
    """
    assert MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_CERTIFICATION == "PROVIDER_CONFIRMED_FAIL_CLOSED_ON_MISMATCH"
    assert isinstance(MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS, str)
    assert len(MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS) > 0
    assert "2026-08-17" in MOTIVE_VEHICLE_UTILIZATION_RESPONSE_MEASUREMENT_SYSTEM_BASIS


def test_vehicle_configured_metric_preference_field_path_is_named() -> None:
    assert MOTIVE_VEHICLE_UTILIZATION_VEHICLE_CONFIGURED_METRIC_PREFERENCE_FIELD_PATH == "vehicle.metric_units"


def test_unit_semantics_contract_block_shape() -> None:
    """Proves the section-18 unit_semantics block's exact shape and that it
    is entirely derived from the existing policy constants -- no new
    certification decision is smuggled in here.
    """
    block = vehicle_utilization_unit_semantics_contract_block()

    assert block["request_header"] == MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER
    assert block["request_header_value"] is True
    assert block["requested_measurement_system"] == "metric"
    assert block["request_policy_certified"] is True
    assert block["canonical_requested_fuel_unit"] == "liters"

    returned = block["returned_vehicle_metric_units_semantics"]
    assert returned["field_path"] == "vehicle.metric_units"
    assert returned["true_means"] == "metric"
    assert returned["false_means"] == "imperial"
    assert returned["equality_with_request_required"] is True

    response = block["response_measurement_system"]
    assert response["classification"] == "PROVIDER_CONFIRMED_FAIL_CLOSED_ON_MISMATCH"
    assert isinstance(response["basis"], str) and response["basis"]

    assert block["time_unit"] == "seconds"
    assert block["mismatch_error_code"] == UNIT_CONTEXT_MISMATCH_ERROR_CODE
    assert block["unit_conversion_enabled"] is False
    assert block["durable_fuel_persistence_ready"] is True


def test_unit_semantics_contract_block_now_explicitly_states_the_confirmed_meaning() -> None:
    """The old, deliberately-neutral gate asserted this block never claimed
    what a returned False meant. That neutrality is now retired on purpose:
    Motive Support has explicitly confirmed the meaning, so the contract
    block must say so plainly rather than staying artificially silent.
    """
    block = vehicle_utilization_unit_semantics_contract_block()
    rendered = " ".join(
        str(value)
        for value in (
            block["returned_vehicle_metric_units_semantics"]["true_means"],
            block["returned_vehicle_metric_units_semantics"]["false_means"],
            block["response_measurement_system"]["classification"],
            block["response_measurement_system"]["basis"],
        )
    ).lower()

    assert "metric" in rendered
    assert "imperial" in rendered
    assert "provider_confirmed" in rendered or "confirmed" in rendered


# ---------------------------------------------------------------------------
# 2026-08-17 account-default unit-request-mode audit gate: the explicit
# 3-value MotiveVehicleUtilizationUnitRequestMode representation. See the
# module docstring for the full rationale -- a plain bool cannot represent
# "no X-Metric-Units header was sent at all".
# ---------------------------------------------------------------------------
def test_unit_request_mode_has_exactly_three_values() -> None:
    assert {mode.value for mode in MotiveVehicleUtilizationUnitRequestMode} == {"metric", "imperial", "account_default"}


def test_account_default_basis_documents_the_fuel_ifta_evidence_without_overclaiming() -> None:
    from app.motive.vehicle_utilization_unit_policy import (
        MOTIVE_VEHICLE_UTILIZATION_UNIT_REQUEST_MODE_ACCOUNT_DEFAULT_BASIS as basis,
    )

    lowered = basis.lower()
    assert "fuel_purchases" in lowered or "fuel/ifta" in lowered
    assert "does not certify" in lowered or "does not" in lowered
    assert "never been made" in lowered or "never" in lowered


@pytest.mark.parametrize(
    ("requested_metric_units", "expected_mode"),
    [(True, METRIC), (False, IMPERIAL)],
)
def test_unit_request_mode_from_bool(requested_metric_units: bool, expected_mode: MotiveVehicleUtilizationUnitRequestMode) -> None:
    assert vehicle_utilization_unit_request_mode_from_bool(requested_metric_units) is expected_mode


@pytest.mark.parametrize("value", [1, 0, "true", "metric", None, []])
def test_unit_request_mode_from_bool_rejects_non_boolean(value: object) -> None:
    with pytest.raises(ValueError, match="explicit Boolean"):
        vehicle_utilization_unit_request_mode_from_bool(value)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Section 3: header emission rule.
#   METRIC          -> X-Metric-Units: true
#   IMPERIAL        -> X-Metric-Units: false
#   ACCOUNT_DEFAULT -> header omitted entirely (represented as None)
# ---------------------------------------------------------------------------
def test_metric_mode_header_value_is_true() -> None:
    assert vehicle_utilization_unit_request_mode_header_value(METRIC) == "true"


def test_imperial_mode_header_value_is_false() -> None:
    assert vehicle_utilization_unit_request_mode_header_value(IMPERIAL) == "false"


def test_account_default_mode_header_value_is_none_meaning_omit_entirely() -> None:
    assert vehicle_utilization_unit_request_mode_header_value(ACCOUNT_DEFAULT) is None


@pytest.mark.parametrize("value", [True, False, "metric", "account_default", None, 1])
def test_unit_request_mode_header_value_rejects_non_enum(value: object) -> None:
    with pytest.raises(ValueError, match="MotiveVehicleUtilizationUnitRequestMode"):
        vehicle_utilization_unit_request_mode_header_value(value)  # type: ignore[arg-type]


def test_unit_request_mode_measurement_system_mapping() -> None:
    assert vehicle_utilization_unit_request_mode_measurement_system(METRIC) == "metric"
    assert vehicle_utilization_unit_request_mode_measurement_system(IMPERIAL) == "imperial"
    assert vehicle_utilization_unit_request_mode_measurement_system(ACCOUNT_DEFAULT) is None


def test_unit_request_mode_expected_fuel_unit_mapping() -> None:
    """ACCOUNT_DEFAULT never invents an expected fuel unit before the
    provider responds -- only METRIC/IMPERIAL have a forced expectation."""
    assert vehicle_utilization_unit_request_mode_expected_fuel_unit(METRIC) == "liters"
    assert vehicle_utilization_unit_request_mode_expected_fuel_unit(IMPERIAL) == "gallons"
    assert vehicle_utilization_unit_request_mode_expected_fuel_unit(ACCOUNT_DEFAULT) is None


# ---------------------------------------------------------------------------
# Persistence-readiness validator with an explicit requested_mode. Section 7
# test matrix: validation.
# ---------------------------------------------------------------------------
def test_metric_mode_true_returned_is_ready() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(True, requested_mode=METRIC)
    assert result.ready_for_durable_persistence is True
    assert result.error_code is None
    assert result.resolved_metric_units is True


def test_metric_mode_false_returned_is_a_mismatch() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(False, requested_mode=METRIC)
    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_CONTEXT_MISMATCH_ERROR_CODE
    assert result.resolved_metric_units is None


def test_imperial_mode_false_returned_is_ready() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(False, requested_mode=IMPERIAL)
    assert result.ready_for_durable_persistence is True
    assert result.error_code is None
    assert result.resolved_metric_units is False


def test_imperial_mode_true_returned_is_a_mismatch() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(True, requested_mode=IMPERIAL)
    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_CONTEXT_MISMATCH_ERROR_CODE
    assert result.resolved_metric_units is None


def test_account_default_mode_true_returned_is_ready_as_metric() -> None:
    """No unit system was forced, so a returned True is simply ready --
    never a 'mismatch' against anything, because Polaris made no request-side
    claim to disagree with."""
    result = validate_vehicle_utilization_unit_persistence_readiness(True, requested_mode=ACCOUNT_DEFAULT)
    assert result.ready_for_durable_persistence is True
    assert result.error_code is None
    assert result.resolved_metric_units is True


def test_account_default_mode_false_returned_is_ready_as_imperial() -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(False, requested_mode=ACCOUNT_DEFAULT)
    assert result.ready_for_durable_persistence is True
    assert result.error_code is None
    assert result.resolved_metric_units is False


def test_account_default_mode_none_returned_still_fails_closed() -> None:
    """Account-default trusts only an explicit, well-formed returned
    Boolean -- a missing indicator is never treated as 'no claim to
    disagree with, so anything goes'."""
    result = validate_vehicle_utilization_unit_persistence_readiness(None, requested_mode=ACCOUNT_DEFAULT)
    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE
    assert result.resolved_metric_units is None


@pytest.mark.parametrize("returned_metric_units", ["true", "false", 1, 0, "metric", "imperial", []])
def test_account_default_mode_malformed_returned_still_fails_closed(returned_metric_units: object) -> None:
    result = validate_vehicle_utilization_unit_persistence_readiness(returned_metric_units, requested_mode=ACCOUNT_DEFAULT)
    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_CONTEXT_INVALID_TYPE_ERROR_CODE
    assert result.resolved_metric_units is None


def test_requested_mode_takes_precedence_over_requested_metric_units() -> None:
    """When both are supplied, the explicit mode wins -- this lets a caller
    migrate to the mode-based call shape without also having to update
    requested_metric_units in lockstep."""
    result = validate_vehicle_utilization_unit_persistence_readiness(
        False, requested_metric_units=True, requested_mode=IMPERIAL
    )
    assert result.ready_for_durable_persistence is True
    assert result.resolved_metric_units is False


def test_invalid_requested_mode_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="MotiveVehicleUtilizationUnitRequestMode"):
        validate_vehicle_utilization_unit_persistence_readiness(True, requested_mode="account_default")  # type: ignore[arg-type]


def test_omitted_requested_mode_derives_from_legacy_boolean_and_matches_prior_behavior() -> None:
    """No requested_mode passed at all (the default) must reproduce the
    exact pre-account-default-gate resolved values for every legacy caller."""
    canonical_true_true = validate_vehicle_utilization_unit_persistence_readiness(True)
    canonical_false_false = validate_vehicle_utilization_unit_persistence_readiness(False, requested_metric_units=False)

    assert canonical_true_true.ready_for_durable_persistence is True
    assert canonical_true_true.resolved_metric_units is True
    assert canonical_false_false.ready_for_durable_persistence is True
    assert canonical_false_false.resolved_metric_units is False


def test_account_default_also_fails_closed_when_certification_kill_switch_reverted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kill switch (MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED)
    gates every mode uniformly, including ACCOUNT_DEFAULT: it is about
    whether the returned Boolean's meaning is trusted at all, independent of
    whether a unit system was forced on the request."""
    import app.motive.vehicle_utilization_unit_policy as unit_policy

    monkeypatch.setattr(unit_policy, "MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED", False)

    result = unit_policy.validate_vehicle_utilization_unit_persistence_readiness(True, requested_mode=ACCOUNT_DEFAULT)

    assert result.ready_for_durable_persistence is False
    assert result.error_code == UNIT_INDICATOR_SEMANTICS_UNRESOLVED_ERROR_CODE
