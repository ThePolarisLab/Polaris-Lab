"""Read-only Motive vehicle-utilization durable writer contract gate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.motive_vehicle_utilization import PARSER_VERSION
from app.connectors.motive_vehicle_utilization_contract import MOTIVE_VEHICLE_UTILIZATION_ENDPOINT
from app.models.motive import MotiveVehicleUtilizationRecord
from app.motive.vehicle_utilization_unit_policy import (
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
    MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
)


LIVE_BOUNDED_EVIDENCE: dict[str, Any] = {
    "evidence_mode": "manual_bounded_read_only",
    "selected_vehicle_count": 3,
    "provider_calls_attempted": 3,
    "provider_calls_completed": 3,
    "max_provider_calls": 3,
    "max_attempts_per_call": 1,
    "page_no": 1,
    "per_page": 3,
    "persistence_enabled": False,
    "checkpoint_advancement_enabled": False,
    "windows": {
        "day_a": {"start_date": "2026-08-12", "end_date": "2026-08-12"},
        "day_b": {"start_date": "2026-08-13", "end_date": "2026-08-13"},
        "combined": {"start_date": "2026-08-12", "end_date": "2026-08-13"},
    },
    "per_window_cardinality": {
        "selected_vehicle_count": 3,
        "returned_unique_selected_vehicle_count": 1,
        "missing_selected_vehicle_count": 2,
        "duplicate_selected_vehicle_rollup_count": 0,
        "unexpected_vehicle_observed": False,
        "pagination_total_present": True,
        "pagination_total_count": 1,
        "returned_item_count": 1,
        "pagination_total_equals_returned_item_count": True,
        "result_truncated_possible": False,
    },
    "overall_cardinality": {
        "one_unique_rollup_per_selected_vehicle_all_windows": False,
        "unexpected_vehicle_observed": False,
        "duplicate_selected_vehicle_rollup_observed": False,
        "result_truncated_possible": False,
        "universal_provider_guarantee": False,
    },
    "vehicle_slot_evidence": {
        "vehicle_slot_1": {"returned_all_windows": False},
        "vehicle_slot_2": {"returned_all_windows": False},
        "vehicle_slot_3": {"returned_all_windows": True},
    },
    "completed_day_composition": {
        "observed_for_one_returned_vehicle": True,
        "additive_metrics_compared": ["idle_time", "driving_time", "idle_fuel", "driving_fuel"],
        "utilization_percentage_added": False,
        "metric_units_consistent_across_windows": True,
        "metric_comparison": {
            "idle_time": "exact_match",
            "driving_time": "exact_match",
            "idle_fuel": "exact_match",
            "driving_fuel": "exact_match",
        },
        "two_single_days_match_combined_window": True,
        "supports_inclusive_date_window_interpretation": True,
        "universal_provider_guarantee": False,
    },
    "no_activity_evidence": {
        "zero_activity_shaped_rollup_observed": False,
        "missing_single_day_rollup_observed": True,
        "missing_combined_window_rollup_observed": True,
        "additive_metric_null_observed": False,
        "no_activity_provider_semantics": "DEFERRED",
        "missing_rollup_means_no_activity": "DEFERRED",
    },
}


def motive_vehicle_utilization_writer_contract_status(db: Session, organization_id: str) -> dict[str, Any]:
    """Return the sanitized durable-writer contract without provider calls or writes."""
    utilization_count = (
        db.query(MotiveVehicleUtilizationRecord)
        .filter(MotiveVehicleUtilizationRecord.organization_id == organization_id)
        .count()
    )
    return {
        "provider": "motive",
        "resource": "vehicle_utilization_writer_contract",
        "source_endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
        "writer_enabled": False,
        "persistence_enabled": False,
        "checkpoint_advancement_enabled": False,
        "scheduled_ingestion_enabled": False,
        "broad_sync_enabled": False,
        "dashboard_daily_brief_attention_enabled": False,
        "live_bounded_evidence": LIVE_BOUNDED_EVIDENCE,
        "returned_row_policy": {
            "classification": "persist_returned_rollups_only_after_validation",
            "creates_rows_from_provider_absence": False,
            "required_conditions": [
                "provider request succeeded",
                "response uses certified vehicle_idle_rollups -> vehicle_idle_rollup envelope",
                "provider vehicle identity maps to exactly one stored MotiveVehicleRecord for the authenticated organization",
                "returned vehicle was included in the requested organization-owned vehicle set",
                "required utilization metrics pass certified parser validation",
                "no duplicate returned rollup exists for the same vehicle and request window",
                "no unexpected provider vehicle appears",
                "pagination is complete for the requested writer page set",
                "fuel metrics retain explicit metric_units context",
            ],
        },
        "missing_row_policy": {
            "classification": "provider_rollup_absent",
            "creates_durable_row": False,
            "creates_synthetic_zero_metrics": False,
            "classifies_vehicle_inactive": False,
            "classifies_no_activity": False,
            "missing_rollup_means_no_activity": "DEFERRED",
            "reason": "Bounded production evidence observed missing requested vehicles, but Motive no-activity semantics are not certified.",
        },
        "unknown_vehicle_policy": {
            "classification": "fail_closed",
            "auto_create_vehicle": False,
            "public_provider_id_exposed": False,
            "reason": "Future writes must attach only to an existing organization-owned MotiveVehicleRecord.",
        },
        "duplicate_policy": {
            "classification": "fail_closed",
            "duplicate_returned_rollup_for_vehicle_window_allowed": False,
            "reason": "A duplicate returned rollup would make one durable row ambiguous.",
        },
        "request_window_identity": {
            "candidate_key": [
                "organization_id",
                "motive_vehicle_id",
                "request_window_start",
                "request_window_end",
            ],
            "provider_natural_key_returned": False,
            "classification": "CERTIFIED_POLARIS_IDEMPOTENCY_KEY",
            "scope": "Preferred Polaris-owned idempotency key for returned, validated rollups from an explicit completed request window.",
            "prefers_internal_vehicle_fk": True,
            "migration_required_now": False,
            "database_enforced": False,
            "writer_enabled": False,
            "persistence_enabled": False,
            "metric_units_in_key": False,
            "reason": "The key is certified as a Polaris-owned replay identity only when the future writer enforces the canonical metric X-Metric-Units policy and fails closed on missing or mismatched returned unit context.",
        },
        "reporting_period_status": {
            "provider_reporting_period_fields_available": False,
            "request_window_start_end_are_context": True,
            "copy_request_window_to_reporting_period": False,
            "reporting_period_start": "DEFERRED",
            "reporting_period_end": "DEFERRED",
        },
        "date_window_contract": {
            "future_writer_may_store_exact_requested_completed_window": True,
            "completed_day_composition_observed_for_returned_vehicle": True,
            "supports_inclusive_date_window_interpretation": True,
            "provider_universal_end_date_guarantee": False,
            "inferred_timestamps_enabled": False,
        },
        "timezone_blocker": {
            "provider_rollup_timezone_behavior": "CONFIRMED_FROM_OFFICIAL_DOCS",
            "exact_company_rollup_timezone": "DEFERRED",
            "exact_company_rollup_timezone_required_before_scheduled_daily_ingestion": True,
            "scheduled_daily_ingestion_enabled": False,
            "automatic_checkpoint_window_calculation_enabled": False,
            "polaris_request_window_calendar_timezone": "America/Winnipeg",
            "polaris_calendar_is_provider_rollup_timezone": False,
        },
        "checkpoint_contract": {
            "enabled": False,
            "must_not_advance_before": [
                "provider request success",
                "certified parser validation",
                "no unexpected returned provider vehicle",
                "no duplicate returned rollup ambiguity",
                "idempotency validation",
                "durable persistence transaction success",
            ],
            "missing_requested_vehicles_create_zero_rows": False,
            "subset_response_can_complete_window_if": [
                "provider response succeeded",
                "pagination is complete",
                "all returned rows are valid",
                "no duplicate returned rows exist",
                "no unexpected vehicles are returned",
                "missing requested vehicles are recorded only as absence diagnostics",
            ],
        },
        "pagination_blocker": {
            "status": "blocked_for_broad_ingestion",
            "live_observation": {
                "pagination_total_present": True,
                "pagination_total_count": 1,
                "returned_item_count": 1,
                "pagination_total_equals_returned_item_count": True,
                "result_truncated_possible": False,
            },
            "broad_writer_requires_explicit_pagination_contract": True,
            "page_2_fetch_enabled": False,
        },
        "unit_policy": {
            "metric_units_preserved": True,
            "writer_unit_mode_certified": True,
            "canonical_metric_units_policy": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_METRIC_UNITS,
            "canonical_unit_system": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_UNIT_SYSTEM,
            "canonical_request_header": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER,
            "canonical_request_header_value": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_WRITER_HEADER_VALUE,
            "canonical_metric_units_policy_required_before_writer_enablement": False,
            "replay_unit_mode_must_not_change_for_existing_window": True,
            "returned_metric_units_must_match_certified_request_policy": True,
            "unknown_or_missing_unit_context_fails_persistence_readiness": True,
            "unit_conversion_enabled": MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
            "combine_fuel_across_different_or_unknown_unit_contexts": False,
            "replay_rule": [
                "canonical requested unit mode remains metric/true for an existing durable vehicle/window identity",
                "returned metric_units must be true",
                "false, missing, or unknown returned unit context fails closed",
                "never overwrite a row using a different unit context",
                "never create a second imperial row",
                "never convert values silently",
            ],
            "reason": "Future durable vehicle-utilization writes use a fixed Polaris-owned metric policy. This does not certify Motive's default behavior when the header is omitted.",
        },
        "observed_persistence_state": {
            "organization_scoped_utilization_rows": utilization_count,
            "existing_nullable_reporting_period_unique_constraint_certified_for_future_writes": False,
        },
        "parser": {
            "version": PARSER_VERSION,
            "certified_envelope": "vehicle_idle_rollups[].vehicle_idle_rollup",
        },
        "security": {
            "organization_scoped": True,
            "provider_ids_exposed": False,
            "vin_values_exposed": False,
            "vehicle_number_values_exposed": False,
            "metric_values_exposed": False,
            "raw_provider_payload_exposed": False,
            "headers_exposed": False,
            "secrets_exposed": False,
        },
        "remaining_blockers": [
            "exact company-configured rollup timezone must be confirmed before scheduled daily ingestion",
            "broad pagination behavior must be certified before ingestion beyond bounded page 1",
            "writer transaction and checkpoint advancement implementation remains disabled",
            "database uniqueness hardening may be addressed in the future writer implementation PR",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
