"""Read-only Motive vehicle field certification for Fleet Operations V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.connectors.motive import MOTIVE_VEHICLES_ENDPOINT
from app.models.motive import MotiveVehicleRecord


@dataclass(frozen=True, slots=True)
class VehicleFieldContract:
    field: str
    provider_path: str | None
    observed_type: str
    persistence_field: str | None
    classification: str
    reason: str
    safe_for_fleet_ui: bool
    safe_for_dashboard_daily_brief: bool
    completeness_field: str | None = None


VEHICLE_FIELD_CONTRACTS: tuple[VehicleFieldContract, ...] = (
    VehicleFieldContract(
        field="provider_vehicle_id",
        provider_path="vehicle.id",
        observed_type="number_or_string_identifier",
        persistence_field="provider_vehicle_id",
        classification="CONFIRMED",
        reason="Official /v1/vehicles documentation defines id as the unique vehicle identifier; Polaris persists it only as tenant-scoped identity.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="provider_vehicle_id",
    ),
    VehicleFieldContract(
        field="vehicle_number",
        provider_path="vehicle.number",
        observed_type="string",
        persistence_field="unit_number",
        classification="CONFIRMED",
        reason="Official /v1/vehicles documentation defines number as the fleet number assigned to the vehicle; Polaris persists it as unit_number.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="unit_number",
    ),
    VehicleFieldContract(
        field="vin",
        provider_path="vehicle.vin",
        observed_type="string",
        persistence_field="vin",
        classification="CONFIRMED",
        reason="Official /v1/vehicles documentation defines vin as the Vehicle Identification Number; safe only inside Fleet UI/detail contexts.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="vin",
    ),
    VehicleFieldContract(
        field="make",
        provider_path="vehicle.make",
        observed_type="string",
        persistence_field="make",
        classification="CONFIRMED",
        reason="Official /v1/vehicles documentation defines make as the vehicle manufacturer.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="make",
    ),
    VehicleFieldContract(
        field="model",
        provider_path="vehicle.model",
        observed_type="string",
        persistence_field="model",
        classification="CONFIRMED",
        reason="Official /v1/vehicles documentation defines model as the vehicle model.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="model",
    ),
    VehicleFieldContract(
        field="year",
        provider_path="vehicle.year",
        observed_type="string_normalized_to_integer_when_valid",
        persistence_field="year",
        classification="CONFIRMED",
        reason="Official /v1/vehicles documentation defines year as the manufacturing year; Polaris stores a valid integer or null.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="year",
    ),
    VehicleFieldContract(
        field="license_plate",
        provider_path="vehicle.license_plate_number",
        observed_type="string",
        persistence_field="license_plate",
        classification="CONFIRMED",
        reason="Official vehicle documentation defines license_plate_number; Polaris persists the plate number without certifying jurisdiction.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="license_plate",
    ),
    VehicleFieldContract(
        field="provider_status",
        provider_path="vehicle.status",
        observed_type="string",
        persistence_field="status",
        classification="CONFIRMED",
        reason="Official /v1/vehicles documentation defines status values such as active/inactive, but Polaris treats this as a Motive literal only.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="status",
    ),
    VehicleFieldContract(
        field="observed_at",
        provider_path="vehicle.updated_at|vehicle.created_at",
        observed_type="datetime",
        persistence_field="observed_at",
        classification="DERIVED",
        reason="Polaris derives observed_at from provider update/create timestamps for sync bookkeeping; it is not a vehicle business field.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="observed_at",
    ),
    VehicleFieldContract(
        field="vehicle_active_inactive_business_state",
        provider_path=None,
        observed_type="not_certified",
        persistence_field=None,
        classification="DEFERRED",
        reason="Motive status is certified only as a provider literal; it is not certified as MOR active, available, dispatched, moving, or in service.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    VehicleFieldContract(
        field="vehicle_driver_association",
        provider_path="vehicle.current_driver",
        observed_type="object",
        persistence_field=None,
        classification="DEFERRED",
        reason="Official docs describe current_driver, but Polaris has not independently certified vehicle-driver association semantics for Fleet V1.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    VehicleFieldContract(
        field="location",
        provider_path="/v1/vehicle_locations.current_location",
        observed_type="object",
        persistence_field=None,
        classification="DEFERRED",
        reason="Location belongs to a separate endpoint and is not part of the current confirmed /v1/vehicles persistence contract.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    VehicleFieldContract(
        field="odometer",
        provider_path="/v1/vehicle_locations.odometer",
        observed_type="number",
        persistence_field=None,
        classification="DEFERRED",
        reason="Odometer belongs to the vehicle_locations contract and is not persisted by the current vehicle ingestion path.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    VehicleFieldContract(
        field="engine_hours",
        provider_path="/v1/vehicle_locations.engine_hours",
        observed_type="number",
        persistence_field=None,
        classification="DEFERRED",
        reason="Engine-hours evidence is from vehicle_locations, not the current /v1/vehicles ingestion contract.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    VehicleFieldContract(
        field="fuel_type",
        provider_path="vehicle.fuel_type",
        observed_type="string",
        persistence_field=None,
        classification="DEFERRED",
        reason="Official vehicle docs define fuel_type, but the existing Polaris schema does not persist it and Fleet V1 does not need it yet.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    VehicleFieldContract(
        field="metric_units",
        provider_path="vehicle.metric_units",
        observed_type="boolean",
        persistence_field=None,
        classification="DEFERRED",
        reason="Official vehicle docs define metric_units, but the current vehicle persistence schema does not store it.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    VehicleFieldContract(
        field="license_plate_state",
        provider_path="vehicle.license_plate_state",
        observed_type="string",
        persistence_field=None,
        classification="DEFERRED",
        reason="Official docs define license_plate_state, but Polaris currently persists only the plate number.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
)


def motive_vehicle_contract_status(db: Session, organization_id: str) -> dict[str, Any]:
    total_vehicles = db.query(MotiveVehicleRecord).filter(MotiveVehicleRecord.organization_id == organization_id).count()
    field_definitions = [_field_definition(contract) for contract in VEHICLE_FIELD_CONTRACTS]
    completeness = {
        contract.field: _completeness(db, organization_id, contract.completeness_field, total_vehicles)
        for contract in VEHICLE_FIELD_CONTRACTS
        if contract.completeness_field
    }

    return {
        "provider": "motive",
        "resource": "vehicle_contract_certification",
        "source_endpoint": MOTIVE_VEHICLES_ENDPOINT,
        "vehicle_count": total_vehicles,
        "field_definitions": field_definitions,
        "completeness": completeness,
        "active_inactive_semantics": {
            "provider_status_literal_certified": True,
            "motive_status_as_mor_business_active_state": "DEFERRED",
            "dashboard_daily_brief_attention_enabled": False,
        },
        "vehicle_driver_association": {
            "classification": "DEFERRED",
            "reason": "Current /v1/vehicles ingestion does not certify durable driver assignment semantics.",
        },
        "persistence": {
            "schema_change_required": False,
            "migration_required": False,
            "identity": "organization_id + provider_vehicle_id",
            "raw_payload_persisted": False,
        },
        "security": {
            "organization_scoped": True,
            "provider_ids_exposed": False,
            "raw_provider_payload_exposed": False,
            "vin_values_exposed": False,
            "license_plate_values_exposed": False,
            "secrets_exposed": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _field_definition(contract: VehicleFieldContract) -> dict[str, Any]:
    return {
        "field": contract.field,
        "provider_name_path": contract.provider_path,
        "observed_type": contract.observed_type,
        "persistence_field": contract.persistence_field,
        "classification": contract.classification,
        "reason": contract.reason,
        "safe_for_fleet_ui": contract.safe_for_fleet_ui,
        "safe_for_dashboard_daily_brief": contract.safe_for_dashboard_daily_brief,
    }


def _completeness(db: Session, organization_id: str, field_name: str | None, total_vehicles: int) -> dict[str, Any]:
    if field_name is None:
        return {"total": total_vehicles, "present": 0, "percent": 0.0}
    column = getattr(MotiveVehicleRecord, field_name)
    query = db.query(func.count(MotiveVehicleRecord.id)).filter(MotiveVehicleRecord.organization_id == organization_id, column.isnot(None))
    if field_name in {"provider_vehicle_id", "unit_number", "vin", "make", "model", "license_plate", "status"}:
        query = query.filter(column != "")
    present = int(query.scalar() or 0)
    percent = round((present / total_vehicles) * 100, 2) if total_vehicles else 0.0
    return {"total": total_vehicles, "present": present, "percent": percent}
