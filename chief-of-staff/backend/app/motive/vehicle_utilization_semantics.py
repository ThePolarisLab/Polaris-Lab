"""Read-only Motive vehicle-utilization semantics certification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.connectors.motive_vehicle_utilization import PARSER_VERSION
from app.connectors.motive_vehicle_utilization_contract import MOTIVE_VEHICLE_UTILIZATION_ENDPOINT
from app.models.motive import MotiveVehicleUtilizationRecord


@dataclass(frozen=True, slots=True)
class UtilizationFieldContract:
    field: str
    provider_path: str | None
    documented_type: str | None
    observed_runtime_type: str | None
    parser_acceptance: str | None
    persistence_field: str | None
    semantic_unit: str | None
    classification: str
    reason: str
    safe_for_fleet_ui: bool
    safe_for_dashboard_daily_brief: bool
    completeness_field: str | None = None


UTILIZATION_FIELD_CONTRACTS: tuple[UtilizationFieldContract, ...] = (
    UtilizationFieldContract(
        field="provider_vehicle_id",
        provider_path="vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.id",
        documented_type="Integer",
        observed_runtime_type="number_or_string_identifier",
        parser_acceptance="non-empty scalar string representation; booleans and complex values rejected",
        persistence_field="provider_vehicle_id",
        semantic_unit=None,
        classification="CONFIRMED",
        reason="Official docs identify vehicle.id as the unique provider vehicle identity; Polaris stores it only as tenant-scoped internal identity.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="provider_vehicle_id",
    ),
    UtilizationFieldContract(
        field="utilization_percent",
        provider_path="vehicle_idle_rollups[].vehicle_idle_rollup.utilization",
        documented_type="String",
        observed_runtime_type="number",
        parser_acceptance="finite numeric JSON number or finite numeric string converted to Decimal",
        persistence_field="utilization_percent",
        semantic_unit="percent",
        classification="CONFIRMED",
        reason="Official docs define utilization as the vehicle utilization rate expressed as a percentage; production observed numeric JSON values.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="utilization_percent",
    ),
    UtilizationFieldContract(
        field="idle_time",
        provider_path="vehicle_idle_rollups[].vehicle_idle_rollup.idle_time",
        documented_type="Integer",
        observed_runtime_type="number",
        parser_acceptance="finite numeric JSON number or finite numeric string converted to Decimal",
        persistence_field="idle_time",
        semantic_unit="seconds",
        classification="CONFIRMED",
        reason="Official docs define idle_time as total idle time in seconds.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="idle_time",
    ),
    UtilizationFieldContract(
        field="driving_time",
        provider_path="vehicle_idle_rollups[].vehicle_idle_rollup.driving_time",
        documented_type="Integer",
        observed_runtime_type="number",
        parser_acceptance="finite numeric JSON number or finite numeric string converted to Decimal",
        persistence_field="driving_time",
        semantic_unit="seconds",
        classification="CONFIRMED",
        reason="Official docs define driving_time as total driving time in seconds.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="driving_time",
    ),
    UtilizationFieldContract(
        field="idle_fuel",
        provider_path="vehicle_idle_rollups[].vehicle_idle_rollup.idle_fuel",
        documented_type="String",
        observed_runtime_type="number",
        parser_acceptance="finite numeric JSON number or finite numeric string converted to Decimal",
        persistence_field="idle_fuel",
        semantic_unit="fuel volume in provider-selected unit system",
        classification="CONFIRMED",
        reason="Official docs define idle_fuel as fuel consumed while idling; unit interpretation remains tied to provider metric/imperial context.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="idle_fuel",
    ),
    UtilizationFieldContract(
        field="driving_fuel",
        provider_path="vehicle_idle_rollups[].vehicle_idle_rollup.driving_fuel",
        documented_type="String",
        observed_runtime_type="number",
        parser_acceptance="finite numeric JSON number or finite numeric string converted to Decimal",
        persistence_field="driving_fuel",
        semantic_unit="fuel volume in provider-selected unit system",
        classification="CONFIRMED",
        reason="Official docs define driving_fuel as fuel consumed while driving; unit interpretation remains tied to provider metric/imperial context.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="driving_fuel",
    ),
    UtilizationFieldContract(
        field="metric_units",
        provider_path="vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.metric_units",
        documented_type="Boolean",
        observed_runtime_type="boolean",
        parser_acceptance="boolean only; non-boolean values are ignored as uncertified",
        persistence_field="metric_units",
        semantic_unit="provider unit-system indicator",
        classification="CONFIRMED",
        reason="Official docs define vehicle.metric_units as a boolean indicating whether metric units are used.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="metric_units",
    ),
    UtilizationFieldContract(
        field="request_window_start",
        provider_path="request.start_date",
        documented_type="date",
        observed_runtime_type="request_context",
        parser_acceptance="external request context only",
        persistence_field="request_window_start",
        semantic_unit="provider-documented summary request scope",
        classification="CONFIRMED_REQUEST_CONTEXT",
        reason="Official docs document start_date as the beginning of the requested utilization summary window; it is not returned as an item reporting-period field.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="request_window_start",
    ),
    UtilizationFieldContract(
        field="request_window_end",
        provider_path="request.end_date",
        documented_type="date",
        observed_runtime_type="request_context",
        parser_acceptance="external request context only",
        persistence_field="request_window_end",
        semantic_unit="provider-documented summary request scope",
        classification="CONFIRMED_REQUEST_CONTEXT",
        reason="Official docs document end_date as the end of the requested utilization summary window; exact boundary inclusivity remains deferred.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="request_window_end",
    ),
    UtilizationFieldContract(
        field="reporting_period_start",
        provider_path=None,
        documented_type=None,
        observed_runtime_type="not_returned",
        parser_acceptance=None,
        persistence_field="reporting_period_start",
        semantic_unit=None,
        classification="DEFERRED",
        reason="The documented v1 response does not return an item-level reporting-period start field; durable period identity remains deferred.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="reporting_period_start",
    ),
    UtilizationFieldContract(
        field="reporting_period_end",
        provider_path=None,
        documented_type=None,
        observed_runtime_type="not_returned",
        parser_acceptance=None,
        persistence_field="reporting_period_end",
        semantic_unit=None,
        classification="DEFERRED",
        reason="The documented v1 response does not return an item-level reporting-period end field; durable period identity remains deferred.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="reporting_period_end",
    ),
    UtilizationFieldContract(
        field="distance",
        provider_path=None,
        documented_type=None,
        observed_runtime_type="not_part_of_current_contract",
        parser_acceptance=None,
        persistence_field="distance",
        semantic_unit=None,
        classification="DEFERRED",
        reason="Distance exists as a legacy persistence column but is not part of the documented v1 vehicle_utilization response contract.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="distance",
    ),
    UtilizationFieldContract(
        field="engine_hours",
        provider_path=None,
        documented_type=None,
        observed_runtime_type="not_part_of_current_contract",
        parser_acceptance=None,
        persistence_field="engine_hours",
        semantic_unit=None,
        classification="DEFERRED",
        reason="Engine hours exists as a legacy persistence column but is not part of the documented v1 vehicle_utilization response contract.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="engine_hours",
    ),
)


def motive_vehicle_utilization_semantics_status(db: Session, organization_id: str) -> dict[str, Any]:
    utilization_count = db.query(MotiveVehicleUtilizationRecord).filter(MotiveVehicleUtilizationRecord.organization_id == organization_id).count()
    field_definitions = [_field_definition(contract) for contract in UTILIZATION_FIELD_CONTRACTS]
    completeness = {
        contract.field: _completeness(db, organization_id, contract.completeness_field, utilization_count)
        for contract in UTILIZATION_FIELD_CONTRACTS
        if contract.completeness_field
    }

    return {
        "provider": "motive",
        "resource": "vehicle_utilization_semantics_certification",
        "source_endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
        "provider_contract": {
            "endpoint_version": "v1",
            "endpoint_kind": "rollup_summary",
            "schema_certified": True,
            "provider_schema_compatibility": "compatible",
            "response_container": "vehicle_idle_rollups",
            "response_wrapper": "vehicle_idle_rollup",
        },
        "request_window": {
            "start_date_parameter": "CONFIRMED",
            "end_date_parameter": "CONFIRMED",
            "summary_scope": "CONFIRMED",
            "end_date_inclusivity": "DEFERRED",
            "provider_returned_reporting_period_fields": False,
        },
        "timezone": {
            "rollup_timezone_behavior": "CONFIRMED",
            "behavior": "company_configured_rollup_timezone",
            "controlled_by_x_time_zone": False,
            "exact_company_rollup_timezone": "DEFERRED",
            "polaris_request_window_calendar_timezone": "America/Winnipeg",
            "polaris_timezone_is_provider_rollup_timezone": False,
        },
        "unit_system": {
            "metric_units_provider_path": "vehicle_idle_rollups[].vehicle_idle_rollup.vehicle.metric_units",
            "metric_units_type": "boolean",
            "x_metric_units_controls_unit_system": "CONFIRMED",
            "normalization_to_one_internal_unit_system": "DEFERRED",
        },
        "field_definitions": field_definitions,
        "completeness": completeness,
        "persistence": {
            "schema_ready_for_future_writer_shape": True,
            "writer_enabled": False,
            "persistence_enabled": False,
            "checkpoint_advancement_enabled": False,
            "scheduled_sync_enabled": False,
            "broad_sync_enabled": False,
            "durable_identity_certified": False,
            "migration_required": False,
            "utilization_records_stored": utilization_count,
            "structural_identity_columns": [
                "organization_id",
                "provider_vehicle_id",
                "motive_vehicle_id",
                "request_window_start",
                "request_window_end",
            ],
            "nullable_period_unique_constraint_certified_for_future_writes": False,
            "blocked_reasons": [
                "end-date boundary behavior is not fully certified",
                "rollup cardinality and no-activity vehicle behavior are unresolved",
                "exact company-configured rollup timezone value is unresolved",
                "durable idempotency key is unresolved",
                "checkpoint advancement strategy is unresolved",
            ],
        },
        "future_evidence_gate": {
            "required": True,
            "mode": "manual_bounded_read_only_probe",
            "must_resolve": [
                "end_date boundary behavior if required for durable keying",
                "returned-row cardinality for requested vehicles",
                "no-activity vehicle behavior",
                "exact company rollup timezone",
                "final durable idempotency identity",
                "checkpoint advancement window",
            ],
            "constraints": {
                "few_vehicles": True,
                "few_requests": True,
                "no_persistence": True,
                "sanitized_output": True,
            },
        },
        "dashboard_daily_brief_boundary": {
            "dashboard_daily_brief_attention_enabled": False,
            "fleet_utilization_cards_enabled": False,
            "normal_certification_state_creates_attention": False,
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
        "parser": {
            "version": PARSER_VERSION,
            "accepts_documented_string_or_integer_metric_forms": True,
            "accepts_observed_numeric_metric_forms": True,
            "zero_values_preserved_distinct_from_null": True,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _field_definition(contract: UtilizationFieldContract) -> dict[str, Any]:
    return {
        "field": contract.field,
        "provider_path": contract.provider_path,
        "documented_type": contract.documented_type,
        "observed_runtime_type": contract.observed_runtime_type,
        "parser_acceptance": contract.parser_acceptance,
        "persistence_field": contract.persistence_field,
        "semantic_unit": contract.semantic_unit,
        "classification": contract.classification,
        "reason": contract.reason,
        "safe_for_fleet_ui": contract.safe_for_fleet_ui,
        "safe_for_dashboard_daily_brief": contract.safe_for_dashboard_daily_brief,
    }


def _completeness(db: Session, organization_id: str, field_name: str | None, total_records: int) -> dict[str, Any]:
    if field_name is None:
        return {"total": total_records, "present": 0, "percent": 0.0}
    column = getattr(MotiveVehicleUtilizationRecord, field_name)
    present = int(
        db.query(func.count(MotiveVehicleUtilizationRecord.id))
        .filter(
            MotiveVehicleUtilizationRecord.organization_id == organization_id,
            column.isnot(None),
        )
        .scalar()
        or 0
    )
    percent = round((present / total_records) * 100, 2) if total_records else 0.0
    return {"total": total_records, "present": present, "percent": percent}
