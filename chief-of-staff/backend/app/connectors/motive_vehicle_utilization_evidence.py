"""Bounded read-only Motive vehicle-utilization runtime evidence probe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging
from typing import Any

import httpx

from app.connectors.motive import MotiveConnectorError
from app.connectors.motive_vehicle_utilization import (
    MotiveVehicleUtilizationParseError,
    MotiveVehicleUtilizationRequestContext,
    MotiveVehicleUtilizationRollup,
    parse_vehicle_utilization_rollups,
)
from app.connectors.motive_vehicle_utilization_contract import (
    MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES,
    MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
    MOTIVE_VEHICLE_UTILIZATION_METRICS,
    request_vehicle_utilization_payload,
)

logger = logging.getLogger(__name__)

MAX_PROVIDER_CALLS = 3
MAX_ATTEMPTS_PER_CALL = 1
ADDITIVE_METRICS = ("idle_time", "driving_time", "idle_fuel", "driving_fuel")
FUEL_METRICS = {"idle_fuel", "driving_fuel"}


@dataclass(frozen=True, slots=True)
class EvidenceWindow:
    key: str
    start_date: date
    end_date: date


def run_vehicle_utilization_bounded_evidence(
    *,
    organization_id: str,
    organization_slug: str,
    provider_vehicle_ids: list[str],
    day_a: date,
    day_b: date,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Perform the bounded three-call evidence probe and return sanitized observations."""
    selected_provider_vehicle_ids = [provider_vehicle_id for provider_vehicle_id in provider_vehicle_ids if provider_vehicle_id][
        :MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES
    ]
    if not selected_provider_vehicle_ids:
        return _failed_result(
            organization_id=organization_id,
            selected_vehicle_count=0,
            windows=[],
            provider_calls_attempted=0,
            provider_calls_completed=0,
            error_code="no_stored_vehicle",
            message="Motive vehicle utilization evidence requires stored Motive vehicles for this organization.",
        )

    windows = [
        EvidenceWindow("day_a", day_a, day_a),
        EvidenceWindow("day_b", day_b, day_b),
        EvidenceWindow("combined", day_a, day_b),
    ]
    selected_slots = {provider_vehicle_id: f"vehicle_slot_{index}" for index, provider_vehicle_id in enumerate(selected_provider_vehicle_ids, start=1)}
    payloads: dict[str, Any] = {}
    parsed_rollups: dict[str, list[MotiveVehicleUtilizationRollup]] = {}
    provider_calls_attempted = 0
    provider_calls_completed = 0

    for window in windows:
        provider_calls_attempted += 1
        try:
            payload, _http_status = request_vehicle_utilization_payload(
                organization_id=organization_id,
                provider_vehicle_ids=selected_provider_vehicle_ids,
                start_date=window.start_date,
                end_date=window.end_date,
                per_page=len(selected_provider_vehicle_ids),
                http_client=http_client,
            )
            provider_calls_completed += 1
        except MotiveConnectorError as exc:
            return _failed_result(
                organization_id=organization_id,
                selected_vehicle_count=len(selected_provider_vehicle_ids),
                windows=windows,
                provider_calls_attempted=provider_calls_attempted,
                provider_calls_completed=provider_calls_completed,
                error_code=exc.code,
                message=str(exc),
            )
        payloads[window.key] = payload
        try:
            parsed_rollups[window.key] = parse_vehicle_utilization_rollups(
                payload,
                organization_id=organization_id,
                organization_slug=organization_slug,
                request_context=MotiveVehicleUtilizationRequestContext(
                    request_start_date=window.start_date,
                    request_end_date=window.end_date,
                ),
            )
        except MotiveVehicleUtilizationParseError as exc:
            return _failed_result(
                organization_id=organization_id,
                selected_vehicle_count=len(selected_provider_vehicle_ids),
                windows=windows,
                provider_calls_attempted=provider_calls_attempted,
                provider_calls_completed=provider_calls_completed,
                error_code=exc.code,
                message="Motive vehicle utilization evidence response did not match the certified provider schema.",
            )

    cardinality = _cardinality(payloads, parsed_rollups, selected_slots, per_page=len(selected_provider_vehicle_ids))
    vehicle_slots = _vehicle_slot_evidence(parsed_rollups, selected_slots)
    composition = _completed_day_composition(parsed_rollups, selected_slots, cardinality)
    no_activity = _no_activity_evidence(vehicle_slots)
    logger.info(
        "MOTIVE VEHICLE UTILIZATION BOUNDED EVIDENCE",
        extra={
            "motive_operation": "vehicle_utilization_bounded_evidence",
            "organization_id": organization_id,
            "selected_vehicle_count": len(selected_provider_vehicle_ids),
            "provider_calls_attempted": provider_calls_attempted,
            "provider_calls_completed": provider_calls_completed,
            "composition": composition["two_single_days_match_combined_window"],
        },
    )
    return {
        "status": "success",
        "provider": "motive",
        "resource": "vehicle_utilization_bounded_evidence",
        "source_endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
        "evidence_mode": "manual_bounded_read_only",
        "request_contract": {
            "selected_vehicle_count": len(selected_provider_vehicle_ids),
            "provider_calls_attempted": provider_calls_attempted,
            "provider_calls_completed": provider_calls_completed,
            "max_provider_calls": MAX_PROVIDER_CALLS,
            "max_attempts_per_call": MAX_ATTEMPTS_PER_CALL,
            "page_no": 1,
            "per_page": len(selected_provider_vehicle_ids),
            "persistence_enabled": False,
            "checkpoint_advancement_enabled": False,
        },
        "windows": _window_payload(windows),
        "cardinality": cardinality,
        "vehicle_slots": vehicle_slots,
        "completed_day_composition": composition,
        "no_activity_evidence": no_activity,
        "timezone_evidence": _timezone_evidence(),
        "pagination_total": _pagination_total(payloads, per_page=len(selected_provider_vehicle_ids)),
        "persistence_readiness": _persistence_readiness(),
        "security": _security_payload(),
        "dashboard_daily_brief_attention_enabled": False,
    }


def _failed_result(
    *,
    organization_id: str,
    selected_vehicle_count: int,
    windows: list[EvidenceWindow],
    provider_calls_attempted: int,
    provider_calls_completed: int,
    error_code: str,
    message: str,
) -> dict[str, Any]:
    logger.info(
        "MOTIVE VEHICLE UTILIZATION BOUNDED EVIDENCE FAILED",
        extra={
            "motive_operation": "vehicle_utilization_bounded_evidence",
            "organization_id": organization_id,
            "selected_vehicle_count": selected_vehicle_count,
            "provider_calls_attempted": provider_calls_attempted,
            "provider_calls_completed": provider_calls_completed,
            "error_code": error_code,
        },
    )
    return {
        "status": "failed",
        "provider": "motive",
        "resource": "vehicle_utilization_bounded_evidence",
        "source_endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
        "evidence_mode": "manual_bounded_read_only",
        "error_code": error_code,
        "message": message,
        "request_contract": {
            "selected_vehicle_count": selected_vehicle_count,
            "provider_calls_attempted": provider_calls_attempted,
            "provider_calls_completed": provider_calls_completed,
            "max_provider_calls": MAX_PROVIDER_CALLS,
            "max_attempts_per_call": MAX_ATTEMPTS_PER_CALL,
            "page_no": 1,
            "per_page": selected_vehicle_count if selected_vehicle_count else None,
            "persistence_enabled": False,
            "checkpoint_advancement_enabled": False,
        },
        "windows": _window_payload(windows),
        "persistence_readiness": _persistence_readiness(),
        "security": _security_payload(),
        "dashboard_daily_brief_attention_enabled": False,
    }


def _cardinality(
    payloads: dict[str, Any],
    parsed_rollups: dict[str, list[MotiveVehicleUtilizationRollup]],
    selected_slots: dict[str, str],
    *,
    per_page: int,
) -> dict[str, Any]:
    windows: dict[str, dict[str, Any]] = {}
    any_unexpected = False
    any_duplicate = False
    any_truncated = False
    all_unique = True
    for window_key, rollups in parsed_rollups.items():
        selected_counts: dict[str, int] = {provider_vehicle_id: 0 for provider_vehicle_id in selected_slots}
        unexpected = False
        for rollup in rollups:
            if rollup.provider_vehicle_id not in selected_slots:
                unexpected = True
                continue
            selected_counts[rollup.provider_vehicle_id] += 1
        duplicate_count = sum(count - 1 for count in selected_counts.values() if count > 1)
        returned_unique_count = sum(1 for count in selected_counts.values() if count > 0)
        missing_count = len(selected_slots) - returned_unique_count
        pagination_total = _pagination_total_value(payloads[window_key])
        truncated = pagination_total is not None and pagination_total > per_page
        any_unexpected = any_unexpected or unexpected
        any_duplicate = any_duplicate or duplicate_count > 0
        any_truncated = any_truncated or truncated
        all_unique = all_unique and not unexpected and duplicate_count == 0 and returned_unique_count == len(selected_slots)
        windows[window_key] = {
            "selected_vehicle_count": len(selected_slots),
            "returned_unique_selected_vehicle_count": returned_unique_count,
            "missing_selected_vehicle_count": missing_count,
            "duplicate_selected_vehicle_rollup_count": duplicate_count,
            "unexpected_vehicle_observed": unexpected,
            "pagination_total_present": pagination_total is not None,
            "pagination_total_count": pagination_total,
            "result_truncated_possible": truncated,
        }
    return {
        "classification": "OBSERVED",
        "windows": windows,
        "returned_row_cardinality": {
            "classification": "OBSERVED",
            "one_unique_rollup_per_selected_vehicle_all_windows": all_unique,
            "universal_provider_guarantee": False,
        },
        "unexpected_vehicle_observed": any_unexpected,
        "duplicate_selected_vehicle_rollup_observed": any_duplicate,
        "result_truncated_possible": any_truncated,
    }


def _vehicle_slot_evidence(
    parsed_rollups: dict[str, list[MotiveVehicleUtilizationRollup]],
    selected_slots: dict[str, str],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for provider_vehicle_id, slot in selected_slots.items():
        evidence[slot] = {}
        for window_key in ("day_a", "day_b", "combined"):
            matching = [rollup for rollup in parsed_rollups.get(window_key, []) if rollup.provider_vehicle_id == provider_vehicle_id]
            rollup = matching[0] if matching else None
            evidence[slot][f"{window_key}_returned"] = bool(rollup)
            evidence[slot][window_key] = _rollup_shape(rollup)
    return evidence


def _rollup_shape(rollup: MotiveVehicleUtilizationRollup | None) -> dict[str, Any]:
    if rollup is None:
        return {
            "rollup_present": False,
            "all_additive_metrics_zero": False,
            "any_additive_metric_nonzero": False,
            "additive_metrics_all_null": None,
            "additive_metric_null_present": None,
        }
    values = [_metric_value(rollup, metric) for metric in ADDITIVE_METRICS]
    non_null = [value for value in values if value is not None]
    return {
        "rollup_present": True,
        "all_additive_metrics_zero": len(non_null) == len(ADDITIVE_METRICS) and all(value == 0 for value in non_null),
        "any_additive_metric_nonzero": any(value != 0 for value in non_null),
        "additive_metrics_all_null": all(value is None for value in values),
        "additive_metric_null_present": any(value is None for value in values),
    }


def _completed_day_composition(
    parsed_rollups: dict[str, list[MotiveVehicleUtilizationRollup]],
    selected_slots: dict[str, str],
    cardinality: dict[str, Any],
) -> dict[str, Any]:
    slot_comparisons: dict[str, Any] = {}
    all_states: list[str] = []
    any_comparable_slot = False
    for provider_vehicle_id, slot in selected_slots.items():
        rollups = {window: _single_selected_rollup(parsed_rollups.get(window, []), provider_vehicle_id) for window in ("day_a", "day_b", "combined")}
        units_consistent = _metric_units_consistency(list(rollups.values()))
        metric_states: dict[str, str] = {}
        for metric in ADDITIVE_METRICS:
            state = _composition_state(metric, rollups["day_a"], rollups["day_b"], rollups["combined"], metric_units_consistent=units_consistent)
            metric_states[metric] = state
            all_states.append(state)
        if all(state in {"exact_match", "within_rounding_bound"} for state in metric_states.values()):
            any_comparable_slot = True
        slot_comparisons[slot] = {
            "metric_units_consistent_across_windows": units_consistent,
            "metrics": metric_states,
        }
    ambiguity = bool(cardinality["unexpected_vehicle_observed"] or cardinality["duplicate_selected_vehicle_rollup_observed"])
    if ambiguity or any(state == "mismatch" for state in all_states):
        match_state = False
        supports_inclusive: bool | str = False
    elif any_comparable_slot:
        match_state = True
        supports_inclusive = True
    else:
        match_state = "indeterminate"
        supports_inclusive = "indeterminate"
    return {
        "classification": "OBSERVED",
        "additive_metrics_compared": list(ADDITIVE_METRICS),
        "utilization_percentage_added": False,
        "rounding_bound_method": "Decimal representation bound: 0.5*quantum(day_a) + 0.5*quantum(day_b) + 0.5*quantum(combined)",
        "two_single_days_match_combined_window": match_state,
        "supports_inclusive_date_window_interpretation": supports_inclusive,
        "universal_provider_guarantee": False,
        "vehicle_slots": slot_comparisons,
    }


def _single_selected_rollup(rollups: list[MotiveVehicleUtilizationRollup], provider_vehicle_id: str) -> MotiveVehicleUtilizationRollup | None:
    matching = [rollup for rollup in rollups if rollup.provider_vehicle_id == provider_vehicle_id]
    return matching[0] if len(matching) == 1 else None


def _metric_units_consistency(rollups: list[MotiveVehicleUtilizationRollup | None]) -> bool | str:
    present = [rollup.metric_units for rollup in rollups if rollup is not None and rollup.metric_units is not None]
    if not present:
        return "indeterminate"
    return len(set(present)) == 1


def _composition_state(
    metric: str,
    day_a: MotiveVehicleUtilizationRollup | None,
    day_b: MotiveVehicleUtilizationRollup | None,
    combined: MotiveVehicleUtilizationRollup | None,
    *,
    metric_units_consistent: bool | str,
) -> str:
    if day_a is None or day_b is None:
        return "indeterminate_missing_rollup"
    if combined is None:
        return "indeterminate_missing_rollup"
    if metric in FUEL_METRICS and metric_units_consistent is False:
        return "indeterminate_unit_mismatch"
    values = [_metric_value(rollup, metric) for rollup in (day_a, day_b, combined)]
    if any(value is None for value in values):
        return "indeterminate_null"
    expected = values[0] + values[1]  # type: ignore[operator]
    actual = values[2]
    if expected == actual:
        return "exact_match"
    bound = _rounding_bound(values[0], values[1], actual)  # type: ignore[arg-type]
    return "within_rounding_bound" if abs(expected - actual) <= bound else "mismatch"


def _metric_value(rollup: MotiveVehicleUtilizationRollup, metric: str) -> Decimal | None:
    return getattr(rollup, metric)


def _rounding_bound(day_a: Decimal, day_b: Decimal, combined: Decimal) -> Decimal:
    return (Decimal("0.5") * _quantum(day_a)) + (Decimal("0.5") * _quantum(day_b)) + (Decimal("0.5") * _quantum(combined))


def _quantum(value: Decimal) -> Decimal:
    exponent = value.as_tuple().exponent
    return Decimal(1).scaleb(exponent if isinstance(exponent, int) else 0)


def _no_activity_evidence(vehicle_slots: dict[str, Any]) -> dict[str, Any]:
    zero_observed = False
    missing_observed = False
    null_observed = False
    for slot in vehicle_slots.values():
        for window_key in ("day_a", "day_b", "combined"):
            window = slot[window_key]
            zero_observed = zero_observed or bool(window["all_additive_metrics_zero"])
            missing_observed = missing_observed or not bool(window["rollup_present"])
            null_observed = null_observed or bool(window["additive_metric_null_present"])
    return {
        "classification": "OBSERVED",
        "zero_activity_shaped_rollup_observed": zero_observed,
        "missing_single_day_rollup_observed": missing_observed,
        "additive_metric_null_observed": null_observed,
        "no_activity_provider_semantics": "DEFERRED",
        "missing_rollup_means_no_activity": "DEFERRED",
    }


def _pagination_total(payloads: dict[str, Any], *, per_page: int) -> dict[str, Any]:
    values = {window: _pagination_total_value(payload) for window, payload in payloads.items()}
    observed = any(value is not None for value in values.values())
    if not observed:
        consistent: bool | str = "indeterminate"
    else:
        consistent = all(value is None or value <= per_page for value in values.values())
    return {
        "observed": observed,
        "values_consistent_with_returned_count": consistent,
        "result_truncated_possible": any(value is not None and value > per_page for value in values.values()),
        "per_window": values,
        "universal_provider_guarantee": False,
    }


def _pagination_total_value(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    pagination = payload.get("pagination")
    if not isinstance(pagination, dict):
        return None
    total = pagination.get("total")
    if isinstance(total, bool):
        return None
    if isinstance(total, int):
        return total
    return None


def _timezone_evidence() -> dict[str, str]:
    return {
        "provider_rollup_timezone_behavior": "CONFIRMED_FROM_OFFICIAL_DOCS",
        "exact_company_rollup_timezone": "DEFERRED",
        "reason": "v1 vehicle_utilization response does not expose sufficient timezone evidence",
        "required_next_evidence": "Motive company/admin configured rollup timezone",
        "polaris_request_window_calendar_timezone": "America/Winnipeg",
        "polaris_calendar_is_provider_rollup_timezone": "false",
    }


def _persistence_readiness() -> dict[str, Any]:
    return {
        "status": "blocked",
        "writer_enabled": False,
        "persistence_enabled": False,
        "durable_identity_certified": False,
        "checkpoint_advancement_enabled": False,
    }


def _security_payload() -> dict[str, bool]:
    return {
        "organization_scoped": True,
        "provider_ids_exposed": False,
        "vin_values_exposed": False,
        "vehicle_number_values_exposed": False,
        "metric_values_exposed": False,
        "raw_provider_payload_exposed": False,
        "headers_exposed": False,
        "secrets_exposed": False,
    }


def _window_payload(windows: list[EvidenceWindow]) -> dict[str, dict[str, str]]:
    return {window.key: {"start_date": window.start_date.isoformat(), "end_date": window.end_date.isoformat()} for window in windows}
