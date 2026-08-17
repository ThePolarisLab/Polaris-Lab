"""Read-only Motive vehicle-utilization durable writer contract gate.

The internal, all-or-nothing writer TRANSACTION PRIMITIVE now exists at
``app.motive.vehicle_utilization_writer.write_vehicle_utilization_transaction``
and is database-enforced via ``uq_motive_vehicle_util_org_vehicle_request_window``.
That module makes zero Motive HTTP calls and is not reachable from any public
route. This status function remains read-only and zero-call/zero-write: it
never imports or calls the writer transaction, and reports only sanitized
metadata about it. Production provider-to-database runtime, the public manual
write route, checkpoint advancement, and scheduled ingestion all remain
disabled.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.motive_vehicle_utilization import PARSER_VERSION
from app.connectors.motive_vehicle_utilization_contract import MOTIVE_VEHICLE_UTILIZATION_ENDPOINT
from app.connectors.motive_vehicle_utilization_pagination import MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE
from app.models.motive import MotiveVehicleUtilizationRecord
from app.motive.vehicle_utilization_controlled_write import (
    CONTROLLED_WRITE_ENABLED_ENV_VAR,
    CONTROLLED_WRITE_MAX_PROVIDER_CALLS,
    CONTROLLED_WRITE_MAX_SELECTED_VEHICLES,
    CONTROLLED_WRITE_WINDOW_END,
    CONTROLLED_WRITE_WINDOW_START,
    controlled_write_enabled,
)
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
    MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED,
    MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
    MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS,
    UNIT_CONTEXT_MISMATCH_ERROR_CODE,
    vehicle_utilization_unit_semantics_contract_block,
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


# ---------------------------------------------------------------------------
# 2026-08-16 gate: sanitized, static evidence from the one real controlled
# production validation executed after PR #162 merged (see
# docs/engineering/MOTIVE_UTILIZATION_UNIT_CONTEXT_EVIDENCE.md). This is
# static metadata only -- it is never dynamically inferred from logs or
# re-derived at runtime, and it carries no provider vehicle ID, VIN,
# utilization value, time value, fuel value, raw provider response, or
# secret of any kind.
#
# 2026-08-17 update: Motive API Support's written reply confirmed that
# X-Metric-Units=true together with a returned vehicle.metric_units=false is
# NOT an expected/documented combination, and directed integrations to fail
# closed. This reclassifies the evidence below from an open
# "semantics unresolved" question to a provider-confirmed unit-context
# mismatch. The sanitized facts themselves (provider_calls, returned
# rollups, records_inserted, checkpoint/history writes, safe_failure) are
# UNCHANGED -- only the classification and reason narrative are updated to
# reflect the new provider confirmation.
# ---------------------------------------------------------------------------
PRODUCTION_WRITE_VALIDATION_EVIDENCE: dict[str, Any] = {
    "execution_date": "2026-08-16",
    "route": "/api/v1/motive/verify/vehicle-utilization-write",
    "fixed_request_window": {"start_date": "2026-08-13", "end_date": "2026-08-13"},
    "selected_vehicle_count": 3,
    "provider_calls_attempted": 1,
    "provider_calls_completed": 1,
    "returned_rollup_count": 1,
    "records_inserted": 0,
    "checkpoint_advanced": False,
    "sync_history_written": False,
    "secrets_exposed": False,
    "status": "failed",
    "error_code": "provider_unit_policy_mismatch",
    "classification": "PROVIDER_CONFIRMED_UNIT_CONTEXT_MISMATCH",
    "previous_classification": "SEMANTICS_UNRESOLVED",
    "failure_stage": "unit_context_readiness",
    "safe_failure": True,
    "reason": (
        "The controlled request explicitly sent X-Metric-Units: true. Motive "
        "returned one rollup that parsed successfully but whose "
        "vehicle.metric_units did not equal True. At the time this was "
        "recorded as an open semantics question. Motive API Support's "
        "2026-08-17 written reply has since confirmed that X-Metric-Units=true "
        "together with a returned vehicle.metric_units=false is not an "
        "expected/documented combination for GET /v1/vehicle_utilization, and "
        "that integrations must fail closed and not persist fuel values when "
        "the requested and returned unit context disagree. Zero durable rows "
        "were written and the route failed closed exactly as designed."
    ),
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
        "writer_transaction_implemented": True,
        "database_enforced": True,
        "runtime_writer_enabled": False,
        "public_manual_write_route_enabled": False,
        "provider_to_database_runtime_enabled": False,
        "writer_transaction": {
            "implemented": True,
            "internal_only": True,
            "module": "app.motive.vehicle_utilization_writer",
            "function": "write_vehicle_utilization_transaction",
            "commits_once": True,
            "all_or_nothing": True,
            "conflicting_replay_policy": "fail_closed",
            "identical_replay_policy": "unchanged",
            "update_existing_row_enabled": False,
            "zero_result_supported": True,
            "provider_calls": 0,
            "checkpoint_writes": 0,
            "sync_history_writes": 0,
            "public_route_enabled": False,
        },
        "historical_rollup_mutability": {
            "classification": "MAY_LEGITIMATELY_DIFFER",
            "provider_confirmed": True,
            "reason": (
                "Motive Support's 2026-08-12 written clarification states that "
                "completed utilization rollups may occasionally be incomplete or "
                "later differ slightly as records are processed, and that "
                "production integrations should periodically re-read a recent "
                "rolling window rather than assume a returned completed aggregate "
                "is permanently immutable. Polaris no longer treats a conflicting "
                "historical value as inherently invalid."
            ),
            "current_runtime_behavior": "identical_replay_unchanged_conflicting_replay_fail_closed_updates_disabled",
            "replay_contract_classification": "TEMPORARY_FAIL_CLOSED_PENDING_RECONCILIATION_POLICY",
            "update_or_upsert_semantics_implemented": False,
            "future_gate_required": True,
            "future_gate_scope": "controlled historical refresh/upsert semantics for broad scheduled ingestion",
        },
        "controlled_manual_write_validation": {
            "implementation_present": True,
            "route_present": True,
            "manual_route": "/api/v1/motive/verify/vehicle-utilization-write",
            "feature_flag": CONTROLLED_WRITE_ENABLED_ENV_VAR,
            "feature_flag_default_enabled": False,
            "feature_flag_currently_enabled": controlled_write_enabled(),
            "production_validation_executed": True,
            "production_validation_succeeded": False,
            "production_validation_persisted_rows": False,
            "production_validation_failure_stage": "unit_context_readiness",
            "production_validation_provider_calls": 1,
            "production_validation_returned_rollups": 1,
            "production_validation_error_code": "provider_unit_policy_mismatch",
            "production_validation_classification": "PROVIDER_CONFIRMED_UNIT_CONTEXT_MISMATCH",
            "production_validation_safe_failure": True,
            "provider_calls_allowed_per_execution": CONTROLLED_WRITE_MAX_PROVIDER_CALLS,
            "selected_vehicle_limit": CONTROLLED_WRITE_MAX_SELECTED_VEHICLES,
            "fixed_validation_window": {
                "start_date": CONTROLLED_WRITE_WINDOW_START.isoformat(),
                "end_date": CONTROLLED_WRITE_WINDOW_END.isoformat(),
            },
            "checkpoint_writes": 0,
            "sync_history_writes": 0,
            "scheduled_ingestion_enabled": False,
        },
        "production_write_validation_evidence": PRODUCTION_WRITE_VALIDATION_EVIDENCE,
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
            "missing_rollup_means_no_activity": "PROVIDER_CONFIRMED_FALSE",
            "provider_confirmed_meaning": "no_matching_rollup_returned_for_requested_range",
            "reason": (
                "Motive Support's 2026-08-12 written clarification confirmed that "
                "vehicles without a matching utilization rollup for the requested "
                "range are simply omitted from the response. Absence means only "
                "that no matching rollup was returned -- it is not proof of "
                "inactivity or no activity, and Polaris still creates no row, no "
                "zero metrics, and no inactive/no-activity classification."
            ),
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
            "database_enforced": True,
            "database_constraint": "uq_motive_vehicle_util_org_vehicle_request_window",
            "database_identity_columns": [
                "organization_id",
                "motive_vehicle_id",
                "request_window_start",
                "request_window_end",
            ],
            "legacy_reporting_period_constraint_retained": True,
            "legacy_reporting_period_constraint_certified_for_future_writer": False,
            "writer_enabled": False,
            "persistence_enabled": False,
            "metric_units_in_key": False,
            "reason": "The key is certified as a Polaris-owned replay identity only when the future writer enforces the canonical metric X-Metric-Units policy and fails closed on missing or mismatched returned unit context. Database uniqueness now enforces this identity for fully-populated rows; the writer itself remains disabled.",
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
            "end_date_inclusive": "PROVIDER_CONFIRMED",
            "one_aggregate_per_vehicle_per_requested_range": "PROVIDER_CONFIRMED",
            "multiple_vehicle_ids_at_most_one_aggregate_per_matching_vehicle": "PROVIDER_CONFIRMED",
            "provider_universal_end_date_guarantee": False,
            "inferred_timestamps_enabled": False,
        },
        "timezone_blocker": {
            "provider_rollup_timezone_behavior": "CONFIRMED_PROVIDER_SUPPORT",
            "company_configured_default_timezone_used": True,
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
            "status": "pagination_reader_certified_writer_still_disabled",
            "pagination_contract_certified": True,
            "pagination_total_meaning": "PROVIDER_CONFIRMED_FILTERED_RESULT_ROW_COUNT",
            "pagination_reader_implemented": True,
            "canonical_page_size": MOTIVE_VEHICLE_UTILIZATION_PAGINATION_CANONICAL_WRITER_PAGE_SIZE,
            "one_based_page_progression": True,
            "pagination_total_required": True,
            "pagination_total_stability_required": True,
            "duplicate_across_pages_fails_closed": True,
            "unexpected_vehicle_fails_closed": True,
            "pagination_persistence_enabled": False,
            "checkpoint_advancement_enabled": False,
            "live_observation": {
                "pagination_total_present": True,
                "pagination_total_count": 1,
                "returned_item_count": 1,
                "pagination_total_equals_returned_item_count": True,
                "result_truncated_possible": False,
            },
            "broad_writer_requires_explicit_pagination_contract": False,
            "page_2_fetch_enabled": False,
        },
        "unit_policy": {
            # -- 2026-08-17 provider-confirmation gate: Motive API Support's
            # written reply confirmed the returned vehicle.metric_units
            # indicator's meaning and the request/response consistency rule.
            # See vehicle_utilization_unit_policy.py and
            # docs/engineering/MOTIVE_UTILIZATION_UNIT_SEMANTICS_CERTIFICATION.md.
            "unit_policy_status": MOTIVE_VEHICLE_UTILIZATION_UNIT_POLICY_STATUS,
            "canonical_request_policy": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY,
            "canonical_requested_unit_system": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUESTED_UNIT_SYSTEM,
            "canonical_request_policy_certified": MOTIVE_VEHICLE_UTILIZATION_CANONICAL_REQUEST_POLICY_CERTIFIED,
            "returned_metric_units_boolean_semantics_certified": MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_BOOLEAN_SEMANTICS_CERTIFIED,
            "returned_metric_units_must_equal_request_boolean": MOTIVE_VEHICLE_UTILIZATION_RETURNED_METRIC_UNITS_MUST_EQUAL_REQUEST_BOOLEAN,
            "durable_fuel_persistence_enabled": MOTIVE_VEHICLE_UTILIZATION_DURABLE_FUEL_PERSISTENCE_ENABLED,
            "unit_conversion_enabled": MOTIVE_VEHICLE_UTILIZATION_UNIT_CONVERSION_ENABLED,
            "combine_fuel_across_unknown_unit_context": MOTIVE_VEHICLE_UTILIZATION_COMBINE_FUEL_ACROSS_UNKNOWN_UNIT_CONTEXT,
            "mismatch_error_code": UNIT_CONTEXT_MISMATCH_ERROR_CODE,
            # -- retained legacy field names/values for compatibility with
            # existing consumers of this endpoint.
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
            "combine_fuel_across_different_or_unknown_unit_contexts": False,
            "replay_rule": [
                "canonical requested unit mode remains metric/true for an existing durable vehicle/window identity",
                "returned metric_units Boolean semantics are provider-confirmed: true means metric, false means imperial",
                "a returned value matching the requested Boolean (true/true or false/false) may become unit-ready",
                "a returned value disagreeing with the requested Boolean fails closed as a provider-confirmed mismatch",
                "a returned None/missing value remains unresolved and fails closed",
                "a non-Boolean, non-None returned value fails closed as a schema/policy error",
                "no fuel-bearing rollup may be durably persisted while the requested and returned unit context disagree",
                "never overwrite a row using a different unit context",
                "never create a second imperial row",
                "never convert values silently",
            ],
            "reason": (
                "Motive API Support's 2026-08-17 written reply confirmed, for "
                "GET /v1/vehicle_utilization: X-Metric-Units=true requests "
                "metric (idle_fuel/driving_fuel in liters); X-Metric-Units=false "
                "requests imperial (gallons); the returned vehicle.metric_units "
                "indicator means true=metric and false=imperial; "
                "idle_time/driving_time are always seconds; and "
                "X-Metric-Units=true together with a returned "
                "vehicle.metric_units=false is not an expected/documented "
                "combination -- integrations must fail closed and not persist "
                "fuel values when the requested and returned unit context "
                "disagree. This upgrades the prior UNRESOLVED classification "
                "to a defined, provider-confirmed, fail-closed-on-mismatch "
                "policy."
            ),
        },
        # -- 2026-08-16 unit-semantics-certification gate: the explicit
        # request-vs-response naming from section 6. This is additive and
        # purely presentational -- it does not change, replace, or duplicate
        # the certification decision made by "unit_policy" above; both
        # blocks are driven by the same underlying policy constants.
        "unit_semantics": vehicle_utilization_unit_semantics_contract_block(),
        "observed_persistence_state": {
            "organization_scoped_utilization_rows": utilization_count,
            "certified_request_window_unique_constraint_enforced": True,
            "existing_nullable_reporting_period_unique_constraint_certified_for_future_writes": False,
            "legacy_nullable_reporting_period_unique_constraint_certified_for_future_writes": False,
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
            "controlled write route remains feature-flagged off by default and requires separate authorization to enable",
            "historical-rollup reconciliation/update policy must be designed before broad rolling-window synchronization",
            "checkpoint advancement implementation remains disabled",
            "exact company-configured Motive timezone value must be confirmed before scheduled daily ingestion",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
