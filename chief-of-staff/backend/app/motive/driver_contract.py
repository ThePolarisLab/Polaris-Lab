"""Read-only Motive company-user field certification for Fleet Operations V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.connectors.motive import MOTIVE_USERS_ENDPOINT
from app.models.motive import MotiveDriverRecord

MOTIVE_DRIVER_ROLE = "driver"
MOTIVE_NON_DRIVER_ROLES = frozenset({"fleet_user", "admin"})
MOTIVE_RECOGNIZED_USER_ROLES = frozenset({MOTIVE_DRIVER_ROLE, *MOTIVE_NON_DRIVER_ROLES})
MOTIVE_DRIVER_ROLE_CLASSIFICATION = "motive_driver_role"
MOTIVE_NON_DRIVER_ROLE_CLASSIFICATION = "motive_non_driver_role"
MOTIVE_UNKNOWN_ROLE_CLASSIFICATION = "unknown_role"


@dataclass(frozen=True, slots=True)
class DriverFieldContract:
    field: str
    provider_path: str | None
    observed_type: str
    persistence_field: str | None
    classification: str
    reason: str
    safe_for_fleet_ui: bool
    safe_for_dashboard_daily_brief: bool
    completeness_field: str | None = None
    metadata_key: str | None = None


DRIVER_FIELD_CONTRACTS: tuple[DriverFieldContract, ...] = (
    DriverFieldContract(
        field="provider_user_id",
        provider_path="user.id",
        observed_type="number_or_string_identifier",
        persistence_field="provider_driver_id",
        classification="CONFIRMED",
        reason="Official /v1/users documentation defines id as the unique user identifier; Polaris persists it only as tenant-scoped identity.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        completeness_field="provider_driver_id",
    ),
    DriverFieldContract(
        field="first_name",
        provider_path="user.first_name",
        observed_type="string",
        persistence_field=None,
        classification="CONFIRMED",
        reason="Official /v1/users documentation defines first_name; Polaris uses it only to derive a combined display name when name is absent.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    DriverFieldContract(
        field="last_name",
        provider_path="user.last_name",
        observed_type="string",
        persistence_field=None,
        classification="CONFIRMED",
        reason="Official /v1/users documentation defines last_name; Polaris uses it only to derive a combined display name when name is absent.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    DriverFieldContract(
        field="full_name",
        provider_path="user.name|user.first_name + user.last_name",
        observed_type="string",
        persistence_field="name",
        classification="DERIVED",
        reason="Polaris stores provider name when present, otherwise combines first_name and last_name; values are personal information.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="name",
    ),
    DriverFieldContract(
        field="email",
        provider_path="user.email",
        observed_type="string_or_null",
        persistence_field="email",
        classification="CONFIRMED",
        reason="Official /v1/users documentation defines email; values are personal information and are not returned by the contract endpoint.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="email",
    ),
    DriverFieldContract(
        field="username",
        provider_path="user.username",
        observed_type="string_or_null",
        persistence_field="provider_payload_metadata.username",
        classification="CONFIRMED",
        reason="Official /v1/users documentation defines username; Polaris stores only metadata, not a dedicated column.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        metadata_key="username",
    ),
    DriverFieldContract(
        field="phone",
        provider_path="user.phone",
        observed_type="string",
        persistence_field=None,
        classification="DEFERRED",
        reason="Official /v1/users documentation defines phone, but Polaris does not persist phone numbers in the current user contract.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    DriverFieldContract(
        field="provider_role",
        provider_path="user.role",
        observed_type="string",
        persistence_field="provider_payload_metadata.role",
        classification="CONFIRMED",
        reason="Official /v1/users documentation defines role values including driver, fleet_user, and admin; Polaris treats this as a provider literal.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        metadata_key="role",
    ),
    DriverFieldContract(
        field="provider_type",
        provider_path="user.type|user.user_type|user.roles",
        observed_type="string_or_array_or_object",
        persistence_field="provider_payload_metadata.type",
        classification="DEFERRED",
        reason="Polaris records selected provider type-like metadata when present, but Fleet V1 has not certified those shapes as driver identity semantics.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
        metadata_key="type",
    ),
    DriverFieldContract(
        field="provider_status",
        provider_path="user.status",
        observed_type="string",
        persistence_field="status",
        classification="CONFIRMED",
        reason="Official /v1/users documentation defines status values such as active/deactivated; Polaris treats this as a Motive literal only.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="status",
    ),
    DriverFieldContract(
        field="observed_at",
        provider_path="user.updated_at|user.created_at",
        observed_type="datetime",
        persistence_field="observed_at",
        classification="DERIVED",
        reason="Polaris derives observed_at from provider update/create timestamps for sync bookkeeping; it is not employment or availability state.",
        safe_for_fleet_ui=True,
        safe_for_dashboard_daily_brief=False,
        completeness_field="observed_at",
    ),
    DriverFieldContract(
        field="driver_classification",
        provider_path="user.role",
        observed_type="string",
        persistence_field="provider_payload_metadata.driver_classification",
        classification="DEFERRED",
        reason="The endpoint returns all company users. Provider role can identify rows whose literal role is driver, but Polaris has not certified every stored row as a driver or a MOR active driver.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    DriverFieldContract(
        field="mor_active_driver_business_state",
        provider_path=None,
        observed_type="not_certified",
        persistence_field=None,
        classification="DEFERRED",
        reason="Motive user status is certified only as a provider literal; it is not certified as MOR employed, active, available, dispatched, HOS-ready, or currently working.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    DriverFieldContract(
        field="vehicle_driver_association",
        provider_path=None,
        observed_type="not_certified",
        persistence_field=None,
        classification="DEFERRED",
        reason="/v1/users ingestion does not persist vehicle assignment and does not certify durable vehicle-driver association semantics.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    DriverFieldContract(
        field="duty_status",
        provider_path="query_param.duty_status|driver_only_fields.duty_status",
        observed_type="string",
        persistence_field=None,
        classification="DEFERRED",
        reason="Motive documents duty_status filtering/driver fields, but Polaris does not persist duty status in the current /v1/users ingestion path.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
    DriverFieldContract(
        field="driver_license",
        provider_path="user.drivers_license_number|user.drivers_license_state",
        observed_type="string",
        persistence_field=None,
        classification="DEFERRED",
        reason="Driver-license fields are sensitive and are not persisted by the current Polaris user contract.",
        safe_for_fleet_ui=False,
        safe_for_dashboard_daily_brief=False,
    ),
)


def motive_driver_contract_status(db: Session, organization_id: str) -> dict[str, Any]:
    total_users = (
        db.query(MotiveDriverRecord)
        .filter(MotiveDriverRecord.organization_id == organization_id, MotiveDriverRecord.source_endpoint == MOTIVE_USERS_ENDPOINT)
        .count()
    )
    field_definitions = [_field_definition(contract) for contract in DRIVER_FIELD_CONTRACTS]
    completeness = {
        contract.field: _completeness(db, organization_id, contract, total_users)
        for contract in DRIVER_FIELD_CONTRACTS
        if contract.completeness_field or contract.metadata_key
    }

    return {
        "provider": "motive",
        "resource": "driver_user_contract_certification",
        "source_endpoint": MOTIVE_USERS_ENDPOINT,
        "company_user_count": total_users,
        "field_definitions": field_definitions,
        "completeness": completeness,
        "driver_classification": {
            "provider_role_literal_certified": True,
            "role_driver_can_distinguish_provider_driver_rows": True,
            "all_users_are_drivers": False,
            "stored_user_as_mor_active_driver": "DEFERRED",
            "driver_classification_certified": False,
            "motive_driver_role_classification_certified": True,
        },
        "active_inactive_semantics": {
            "provider_status_literal_certified": True,
            "motive_status_as_mor_active_driver_state": "DEFERRED",
            "dashboard_daily_brief_attention_enabled": False,
        },
        "vehicle_driver_association": {
            "classification": "DEFERRED",
            "reason": "Current /v1/users ingestion does not certify durable vehicle assignment semantics.",
        },
        "persistence": {
            "schema_change_required": False,
            "migration_required": False,
            "identity": "organization_id + provider_driver_id",
            "table_name_note": "motive_drivers stores Motive company users; driver classification remains deferred.",
            "raw_payload_persisted": False,
        },
        "security": {
            "organization_scoped": True,
            "provider_ids_exposed": False,
            "email_values_exposed": False,
            "phone_values_exposed": False,
            "raw_provider_payload_exposed": False,
            "secrets_exposed": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def motive_driver_classification_status(db: Session, organization_id: str) -> dict[str, Any]:
    rows = (
        db.query(MotiveDriverRecord.provider_payload_metadata)
        .filter(MotiveDriverRecord.organization_id == organization_id, MotiveDriverRecord.source_endpoint == MOTIVE_USERS_ENDPOINT)
        .all()
    )
    total_users = len(rows)
    counts = {
        "total_company_users": total_users,
        "rows_with_role": 0,
        "motive_driver_role_count": 0,
        "non_driver_role_count": 0,
        "unknown_or_missing_role_count": 0,
        "unknown_undocumented_role_count": 0,
    }
    for (metadata,) in rows:
        outcome = classify_motive_user_role(metadata)
        if _metadata_value_present(metadata, "role"):
            counts["rows_with_role"] += 1
        if outcome == MOTIVE_DRIVER_ROLE_CLASSIFICATION:
            counts["motive_driver_role_count"] += 1
        elif outcome == MOTIVE_NON_DRIVER_ROLE_CLASSIFICATION:
            counts["non_driver_role_count"] += 1
        else:
            counts["unknown_or_missing_role_count"] += 1
            if _metadata_value_present(metadata, "role"):
                counts["unknown_undocumented_role_count"] += 1

    return {
        "provider": "motive",
        "resource": "driver_role_classification_certification",
        "source_endpoint": MOTIVE_USERS_ENDPOINT,
        "classification_definition": {
            MOTIVE_DRIVER_ROLE_CLASSIFICATION: 'provider_payload_metadata.role normalized to "driver"',
            MOTIVE_NON_DRIVER_ROLE_CLASSIFICATION: 'provider_payload_metadata.role normalized to "fleet_user" or "admin"',
            MOTIVE_UNKNOWN_ROLE_CLASSIFICATION: "missing, blank, non-string, or undocumented provider role",
        },
        "certification": {
            "motive_driver_role_classification_certified": True,
            "mor_business_driver_certified": False,
            "mor_active_driver_certified": False,
            "vehicle_driver_association_certified": False,
        },
        "recognized_provider_roles": sorted(MOTIVE_RECOGNIZED_USER_ROLES),
        "counts": counts,
        "active_driver_safeguard": {
            "role_driver_plus_status_active_means_mor_active_driver": False,
            "reason": "Provider role and provider status are certified only as Motive literals; MOR employment, availability, dispatch, HOS, and working state remain deferred.",
        },
        "vehicle_driver_association": {
            "classification": "DEFERRED",
            "reason": "Role classification does not assign vehicles or certify durable vehicle-driver association.",
        },
        "persistence": {
            "schema_change_required": False,
            "migration_required": False,
            "classification_source": "provider_payload_metadata.role",
            "computed_read_only": True,
        },
        "dashboard_daily_brief_boundary": {
            "fleet_attention_enabled": False,
            "driver_count_cards_enabled": False,
            "normal_state_creates_attention": False,
        },
        "security": {
            "organization_scoped": True,
            "provider_ids_exposed": False,
            "names_exposed": False,
            "email_values_exposed": False,
            "username_values_exposed": False,
            "phone_values_exposed": False,
            "raw_metadata_exposed": False,
            "raw_provider_payload_exposed": False,
            "secrets_exposed": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def classify_motive_user_role(metadata: Any) -> str:
    role = _normalized_provider_role(metadata)
    if role == MOTIVE_DRIVER_ROLE:
        return MOTIVE_DRIVER_ROLE_CLASSIFICATION
    if role in MOTIVE_NON_DRIVER_ROLES:
        return MOTIVE_NON_DRIVER_ROLE_CLASSIFICATION
    return MOTIVE_UNKNOWN_ROLE_CLASSIFICATION


def _field_definition(contract: DriverFieldContract) -> dict[str, Any]:
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


def _completeness(db: Session, organization_id: str, contract: DriverFieldContract, total_users: int) -> dict[str, Any]:
    if contract.completeness_field:
        column = getattr(MotiveDriverRecord, contract.completeness_field)
        query = db.query(func.count(MotiveDriverRecord.id)).filter(
            MotiveDriverRecord.organization_id == organization_id,
            MotiveDriverRecord.source_endpoint == MOTIVE_USERS_ENDPOINT,
            column.isnot(None),
        )
        if contract.completeness_field in {"provider_driver_id", "name", "email", "status"}:
            query = query.filter(column != "")
        present = int(query.scalar() or 0)
    elif contract.metadata_key:
        rows = (
            db.query(MotiveDriverRecord.provider_payload_metadata)
            .filter(MotiveDriverRecord.organization_id == organization_id, MotiveDriverRecord.source_endpoint == MOTIVE_USERS_ENDPOINT)
            .all()
        )
        present = sum(1 for (metadata,) in rows if _metadata_value_present(metadata, contract.metadata_key))
    else:
        present = 0
    percent = round((present / total_users) * 100, 2) if total_users else 0.0
    return {"total": total_users, "present": present, "percent": percent}


def _metadata_value_present(metadata: Any, key: str) -> bool:
    if not isinstance(metadata, dict):
        return False
    value = metadata.get(key)
    if value is None or value == "":
        return False
    return True


def _normalized_provider_role(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    role = metadata.get("role")
    if not isinstance(role, str):
        return None
    normalized = role.strip().lower()
    return normalized or None
