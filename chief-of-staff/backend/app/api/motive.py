"""Authenticated Motive connector APIs for Company API Key verification and narrow ingestion."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.motive import (
    MOTIVE_AUTHENTICATION_METHOD,
    MOTIVE_CONFIRMED_ENDPOINTS,
    MOTIVE_CREDENTIAL_SOURCE,
    MOTIVE_USERS_ENDPOINT,
    MOTIVE_USERS_PER_PAGE,
    MOTIVE_VEHICLES_ENDPOINT,
    MOTIVE_VEHICLES_PER_PAGE,
    MOTIVE_VERIFICATION_ENDPOINT,
    MOTIVE_VERIFICATION_PARAMS,
    MotiveConnector,
    MotiveConnectorError,
)
from app.connectors.motive_contracts import MotiveDriver, MotiveVehicle
from app.connectors.motive_vehicle_utilization_contract import (
    MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
    MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES,
    MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE,
    run_vehicle_utilization_contract_verification,
)
from app.connectors.motive_vehicle_utilization_evidence import run_vehicle_utilization_bounded_evidence
from app.database.database import SessionLocal
from app.models.motive import MotiveDriverRecord, MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord
from app.motive.driver_contract import motive_driver_classification_status, motive_driver_contract_status
from app.motive.fleet_foundation import motive_fleet_foundation_status
from app.motive.vehicle_contract import motive_vehicle_contract_status
from app.motive.vehicle_utilization_semantics import motive_vehicle_utilization_semantics_status
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/motive", tags=["motive"])
_DATABASE_PERSISTENCE_ERROR_CODE = "database_persistence_error"
_DATABASE_VEHICLE_PERSISTENCE_ERROR_MESSAGE = "Motive vehicle sync failed during database persistence."
_DATABASE_USER_PERSISTENCE_ERROR_MESSAGE = "Motive user sync failed during database persistence."


def _db() -> Session:
    with SessionLocal() as session:
        yield session


def _connector(organization_id: str) -> MotiveConnector:
    return MotiveConnector(organization_id=organization_id)


@router.get("/status")
def motive_status(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    connector = _connector(principal.organization_id)
    persisted_status = _latest_motive_status(session, principal.organization_id)
    status_payload = connector.safe_status(persisted_status=persisted_status)
    logger.info(
        "MOTIVE API KEY STATUS READ",
        extra={
            "motive_operation": "status",
            "organization_id": principal.organization_id,
            "key_present": bool(status_payload.get("key_present")),
            "connection_status": status_payload.get("connection_status"),
            "authorization_required": status_payload.get("authorization_required"),
        },
    )
    return {"health": connector.health(persisted_status=persisted_status).model_dump(mode="json"), "status": status_payload}


@router.get("/connect")
def motive_connect(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE))) -> dict[str, Any]:
    """OAuth authorization is disabled for the Mor Logistics Company API Key architecture."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error_code": "oauth_disabled",
            "message": "Motive OAuth connect is disabled. Motive uses administrator-managed Company API Key configuration.",
            "authentication_method": MOTIVE_AUTHENTICATION_METHOD,
            "secrets_exposed": False,
        },
    )


@router.get("/oauth/callback")
def motive_callback() -> dict[str, Any]:
    """Dormant OAuth callback retained only to fail safely while deployed routes settle."""
    logger.info("MOTIVE OAUTH CALLBACK DISABLED", extra={"motive_operation": "oauth_disabled"})
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error_code": "oauth_disabled",
            "message": "Motive OAuth callback is disabled. Motive production authentication uses Company API Key.",
            "secrets_exposed": False,
        },
    )


@router.post("/verify")
def verify_motive_connection(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one narrow read-only Motive Company API Key verification request for the active organization."""
    organization = _organization(session, principal.organization_id)
    started_at = datetime.now(timezone.utc)
    run_id = f"motive-verify-{uuid4()}"
    history = MotiveSyncHistory(
        organization_id=principal.organization_id,
        organization_slug=organization.slug,
        provider="motive",
        provider_resource="vehicles",
        mode="verification",
        status="running",
        run_id=run_id,
        started_at=started_at,
        checkpoint_before={},
        checkpoint_after={},
        resource_counts={},
    )
    session.add(history)
    session.commit()
    try:
        result = _connector(principal.organization_id).verify_connection()
    except MotiveConnectorError as exc:
        _mark_history_failure(session, history, exc, checkpoint_before={})
        raise HTTPException(status_code=_http_status(exc), detail={"status": exc.status.value, "error_code": exc.code, "message": str(exc)}) from exc
    history.status = "success"
    history.completed_at = datetime.now(timezone.utc)
    history.records_read = int(result.get("records_read") or 0)
    history.records_written = 0
    history.resource_counts = {"vehicles": history.records_read}
    history.checkpoint_after = history.checkpoint_before
    session.commit()
    return {**result, "run_id": run_id}


@router.post("/verify/vehicle-utilization-contract")
def verify_motive_vehicle_utilization_contract(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one temporary read-only contract probe for Motive vehicle utilization."""
    _organization(session, principal.organization_id)
    vehicles = _vehicles_for_utilization_contract(session, principal.organization_id)
    if not vehicles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "status": "failed",
                "resource": "vehicle_utilization_contract",
                "error_code": "no_stored_vehicle",
                "message": "Motive vehicle utilization contract verification requires one stored Motive vehicle for this organization.",
                "secrets_exposed": False,
            },
        )
    start_date, end_date = _completed_vehicle_utilization_contract_window()
    try:
        result = run_vehicle_utilization_contract_verification(
            organization_id=principal.organization_id,
            provider_vehicle_ids=[vehicle.provider_vehicle_id for vehicle in vehicles],
            start_date=start_date,
            end_date=end_date,
        )
    except MotiveConnectorError as exc:
        detail = {
            "status": exc.status.value,
            "resource": "vehicle_utilization_contract",
            "error_code": exc.code,
            "message": str(exc),
            "secrets_exposed": False,
        }
        provider_diagnostics = getattr(exc, "provider_diagnostics", None)
        if isinstance(provider_diagnostics, dict):
            detail.update(provider_diagnostics)
        raise HTTPException(status_code=_http_status(exc), detail=detail) from exc
    logger.info(
        "MOTIVE VEHICLE UTILIZATION CONTRACT VERIFY",
        extra={
            "motive_operation": "vehicle_utilization_contract_verify",
            "organization_id": principal.organization_id,
            "http_status": 200,
            "response_type": result.get("top_level_type"),
            "item_count": result.get("item_count_observed"),
            "schema_compatibility": result.get("schema_compatibility"),
        },
    )
    return result


@router.post("/verify/vehicle-utilization-evidence")
def verify_motive_vehicle_utilization_evidence(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run a bounded three-window read-only evidence probe for Motive vehicle utilization."""
    organization = _organization(session, principal.organization_id)
    vehicles = _vehicles_for_utilization_contract(session, principal.organization_id)
    if not vehicles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "status": "failed",
                "resource": "vehicle_utilization_bounded_evidence",
                "error_code": "no_stored_vehicle",
                "message": "Motive vehicle utilization evidence requires stored Motive vehicles for this organization.",
                "provider_calls_attempted": 0,
                "provider_calls_completed": 0,
                "secrets_exposed": False,
            },
        )
    day_a, day_b = _completed_vehicle_utilization_evidence_days()
    result = run_vehicle_utilization_bounded_evidence(
        organization_id=principal.organization_id,
        organization_slug=organization.slug,
        provider_vehicle_ids=[vehicle.provider_vehicle_id for vehicle in vehicles],
        day_a=day_a,
        day_b=day_b,
    )
    logger.info(
        "MOTIVE VEHICLE UTILIZATION BOUNDED EVIDENCE",
        extra={
            "motive_operation": "vehicle_utilization_bounded_evidence",
            "organization_id": principal.organization_id,
            "selected_vehicle_count": result.get("request_contract", {}).get("selected_vehicle_count"),
            "provider_calls_attempted": result.get("request_contract", {}).get("provider_calls_attempted"),
            "provider_calls_completed": result.get("request_contract", {}).get("provider_calls_completed"),
            "status": result.get("status"),
        },
    )
    return result


@router.post("/sync/vehicles")
def sync_motive_vehicles(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one manual read-only vehicle ingestion for the active organization."""
    organization = _organization(session, principal.organization_id)
    checkpoint = _resource_checkpoint(session, principal.organization_id, "vehicles")
    checkpoint_before = _checkpoint_snapshot(checkpoint)
    started_at = datetime.now(timezone.utc)
    run_id = f"motive-vehicles-{uuid4()}"
    history = _create_running_history(session, organization, run_id=run_id, provider_resource="vehicles", mode="vehicle_sync", checkpoint_before=checkpoint_before, started_at=started_at)
    try:
        result = _connector(principal.organization_id).list_vehicles(organization_id=principal.organization_id, organization_slug=organization.slug)
        counts = _upsert_vehicles(session, result["vehicles"])
        completed_at = datetime.now(timezone.utc)
        checkpoint_after = _checkpoint_after(result, completed_at)
        checkpoint = _ensure_resource_checkpoint(session, organization, "vehicles")
        _mark_checkpoint_success(checkpoint, checkpoint_after, completed_at)
        _mark_history_success(history, result=result, counts=counts, checkpoint_after=checkpoint_after, completed_at=completed_at, resource="vehicles")
        session.commit()
    except MotiveConnectorError as exc:
        session.rollback()
        history = session.query(MotiveSyncHistory).filter(MotiveSyncHistory.run_id == run_id).one()
        _mark_history_failure(session, history, exc, checkpoint_before=checkpoint_before, resource="vehicles")
        raise HTTPException(status_code=_http_status(exc), detail={"status": exc.status.value, "resource": "vehicles", "error_code": exc.code, "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        _mark_persistence_failure(session, run_id=run_id, checkpoint_before=checkpoint_before, resource="vehicles", message=_DATABASE_VEHICLE_PERSISTENCE_ERROR_MESSAGE)
        raise _persistence_http_exception("vehicles", _DATABASE_VEHICLE_PERSISTENCE_ERROR_MESSAGE) from exc
    response = _sync_response(result=result, counts=counts, history=history, resource="vehicles", certified_field="vehicle_ingestion_certified")
    logger.info(
        "MOTIVE VEHICLES SYNC SUCCESS",
        extra={
            "motive_operation": "vehicle_sync",
            "organization_id": principal.organization_id,
            "endpoint_path": MOTIVE_VEHICLES_ENDPOINT,
            "pages_read": response["pages_read"],
            "records_read": response["records_read"],
            "records_upserted": response["records_upserted"],
        },
    )
    return response


@router.post("/sync/users")
def sync_motive_users(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one manual read-only company-user ingestion for the active organization."""
    organization = _organization(session, principal.organization_id)
    checkpoint = _resource_checkpoint(session, principal.organization_id, "users")
    checkpoint_before = _checkpoint_snapshot(checkpoint)
    started_at = datetime.now(timezone.utc)
    run_id = f"motive-users-{uuid4()}"
    history = _create_running_history(session, organization, run_id=run_id, provider_resource="users", mode="user_sync", checkpoint_before=checkpoint_before, started_at=started_at)
    try:
        result = _connector(principal.organization_id).list_users(organization_id=principal.organization_id, organization_slug=organization.slug)
        counts = _upsert_users(session, result["users"])
        completed_at = datetime.now(timezone.utc)
        checkpoint_after = _checkpoint_after(result, completed_at)
        checkpoint = _ensure_resource_checkpoint(session, organization, "users")
        _mark_checkpoint_success(checkpoint, checkpoint_after, completed_at)
        _mark_history_success(history, result=result, counts=counts, checkpoint_after=checkpoint_after, completed_at=completed_at, resource="users")
        session.commit()
    except MotiveConnectorError as exc:
        session.rollback()
        history = session.query(MotiveSyncHistory).filter(MotiveSyncHistory.run_id == run_id).one()
        _mark_history_failure(session, history, exc, checkpoint_before=checkpoint_before, resource="users")
        raise HTTPException(status_code=_http_status(exc), detail={"status": exc.status.value, "resource": "users", "error_code": exc.code, "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        _mark_persistence_failure(session, run_id=run_id, checkpoint_before=checkpoint_before, resource="users", message=_DATABASE_USER_PERSISTENCE_ERROR_MESSAGE)
        raise _persistence_http_exception("users", _DATABASE_USER_PERSISTENCE_ERROR_MESSAGE) from exc
    response = _sync_response(result=result, counts=counts, history=history, resource="users", certified_field="user_ingestion_certified")
    response["driver_classification_certified"] = False
    logger.info(
        "MOTIVE USERS SYNC SUCCESS",
        extra={
            "motive_operation": "user_sync",
            "organization_id": principal.organization_id,
            "endpoint_path": MOTIVE_USERS_ENDPOINT,
            "pages_read": response["pages_read"],
            "records_read": response["records_read"],
            "records_upserted": response["records_upserted"],
            "driver_classification_certified": False,
        },
    )
    return response


@router.post("/disconnect")
def disconnect_motive(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE))) -> dict[str, Any]:
    return {
        "disconnected": False,
        "organization_id": principal.organization_id,
        "configuration_managed_by": "administrator_environment",
        "message": "Motive Company API Key is managed in backend environment configuration. Remove the backend secret to disconnect.",
        "secrets_exposed": False,
    }


@router.get("/verification-contract")
def motive_verification_contract(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    return {
        "provider": "motive",
        "authentication_method": MOTIVE_AUTHENTICATION_METHOD,
        "credential_source": MOTIVE_CREDENTIAL_SOURCE,
        "credential_configuration": "administrator_backend_environment",
        "request_authentication": "company_api_key_header_at_provider_boundary",
        "confirmed_endpoints": list(MOTIVE_CONFIRMED_ENDPOINTS),
        "driver_user_pagination": {"endpoint": MOTIVE_USERS_ENDPOINT, "per_page_max": MOTIVE_USERS_PER_PAGE, "page_no": "one_based", "total_field": "pagination.total"},
        "verification_endpoint": MOTIVE_VERIFICATION_ENDPOINT,
        "verification_request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": dict(MOTIVE_VERIFICATION_PARAMS), "authentication": "company_api_key_header"},
        "vehicle_sync": {"method": "GET", "path": MOTIVE_VEHICLES_ENDPOINT, "params": {"per_page": MOTIVE_VEHICLES_PER_PAGE, "page_no": "one_based"}, "manual_route": "/api/v1/motive/sync/vehicles"},
        "fleet_vehicle_contract": {
            "method": "GET",
            "manual_route": "/api/v1/motive/fleet/vehicle-contract",
            "source_endpoint": MOTIVE_VEHICLES_ENDPOINT,
            "persistence_identity": "organization_id + provider_vehicle_id",
            "raw_provider_payload_exposed": False,
            "dashboard_daily_brief_attention_enabled": False,
        },
        "user_sync": {"method": "GET", "path": MOTIVE_USERS_ENDPOINT, "params": {"per_page": MOTIVE_USERS_PER_PAGE, "page_no": "one_based"}, "manual_route": "/api/v1/motive/sync/users", "driver_classification_certified": False},
        "fleet_driver_contract": {
            "method": "GET",
            "manual_route": "/api/v1/motive/fleet/driver-contract",
            "source_endpoint": MOTIVE_USERS_ENDPOINT,
            "persistence_identity": "organization_id + provider_driver_id",
            "driver_classification_certified": False,
            "raw_provider_payload_exposed": False,
            "dashboard_daily_brief_attention_enabled": False,
        },
        "fleet_driver_classification": {
            "method": "GET",
            "manual_route": "/api/v1/motive/fleet/driver-classification",
            "source_endpoint": MOTIVE_USERS_ENDPOINT,
            "classification_source": "provider_payload_metadata.role",
            "motive_driver_role_classification_certified": True,
            "mor_active_driver_certified": False,
            "raw_provider_payload_exposed": False,
            "dashboard_daily_brief_attention_enabled": False,
        },
        "vehicle_utilization_contract_verification": {
            "method": "GET",
            "path": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
            "manual_route": "/api/v1/motive/verify/vehicle-utilization-contract",
            "params": {
                "vehicle_ids[]": "up_to_three_redacted_stored_vehicle_ids",
                "start_date": "one_calendar_day_before_previous_completed_calendar_day",
                "end_date": "previous_completed_calendar_day",
                "per_page": 1,
                "page_no": 1,
            },
            "max_provider_attempts": 1,
            "max_provider_vehicles": MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES,
            "persistence_enabled": False,
        },
        "fleet_vehicle_utilization_semantics": {
            "method": "GET",
            "manual_route": "/api/v1/motive/fleet/vehicle-utilization-semantics",
            "source_endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
            "provider_schema_compatibility": "compatible",
            "persistence_enabled": False,
            "checkpoint_advancement_enabled": False,
            "dashboard_daily_brief_attention_enabled": False,
        },
        "vehicle_utilization_bounded_evidence": {
            "method": "POST",
            "manual_route": "/api/v1/motive/verify/vehicle-utilization-evidence",
            "source_endpoint": MOTIVE_VEHICLE_UTILIZATION_ENDPOINT,
            "provider_calls_per_successful_run": 3,
            "max_provider_vehicles": MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES,
            "page_no": 1,
            "persistence_enabled": False,
            "checkpoint_advancement_enabled": False,
            "dashboard_daily_brief_attention_enabled": False,
        },
        "oauth_runtime_enabled": False,
        "broad_sync_enabled": False,
        "production_certified": False,
        "vehicle_ingestion_certified_only_after_successful_manual_sync": True,
        "user_ingestion_certified_only_after_successful_manual_sync": True,
        "secrets_exposed": False,
    }


@router.get("/fleet/foundation")
def motive_fleet_foundation(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return the read-only Motive Fleet V1 production contract and persistence gate."""
    _organization(session, principal.organization_id)
    return motive_fleet_foundation_status(session, principal.organization_id)


@router.get("/fleet/vehicle-contract")
def motive_fleet_vehicle_contract(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return read-only Motive vehicle field certification for Fleet Operations V1."""
    _organization(session, principal.organization_id)
    return motive_vehicle_contract_status(session, principal.organization_id)


@router.get("/fleet/driver-contract")
def motive_fleet_driver_contract(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return read-only Motive company-user field certification for Fleet Operations V1."""
    _organization(session, principal.organization_id)
    return motive_driver_contract_status(session, principal.organization_id)


@router.get("/fleet/driver-classification")
def motive_fleet_driver_classification(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return read-only Motive provider-role classification counts for Fleet Operations V1."""
    _organization(session, principal.organization_id)
    return motive_driver_classification_status(session, principal.organization_id)


@router.get("/fleet/vehicle-utilization-semantics")
def motive_fleet_vehicle_utilization_semantics(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return read-only Motive vehicle-utilization semantics certification."""
    _organization(session, principal.organization_id)
    return motive_vehicle_utilization_semantics_status(session, principal.organization_id)


def _organization(session: Session, organization_id: str) -> Organization:
    organization = session.query(Organization).filter(Organization.id == organization_id).one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


def _vehicles_for_utilization_contract(session: Session, organization_id: str) -> list[MotiveVehicleRecord]:
    return (
        session.query(MotiveVehicleRecord)
        .filter(MotiveVehicleRecord.organization_id == organization_id)
        .order_by(MotiveVehicleRecord.id.asc())
        .limit(MOTIVE_VEHICLE_UTILIZATION_CONTRACT_MAX_VEHICLES)
        .all()
    )


def _completed_vehicle_utilization_contract_window() -> tuple[date, date]:
    company_today = datetime.now(ZoneInfo(MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE)).date()
    end_date = company_today - timedelta(days=1)
    start_date = end_date - timedelta(days=1)
    return start_date, end_date


def _completed_vehicle_utilization_evidence_days() -> tuple[date, date]:
    company_today = datetime.now(ZoneInfo(MOTIVE_VEHICLE_UTILIZATION_REQUEST_WINDOW_TIME_ZONE)).date()
    day_a = company_today - timedelta(days=3)
    day_b = company_today - timedelta(days=2)
    return day_a, day_b


def _latest_motive_status(session: Session, organization_id: str) -> dict[str, Any] | None:
    verification = _latest_history(session, organization_id, mode="verification")
    vehicle_sync = _latest_history(session, organization_id, mode="vehicle_sync")
    user_sync = _latest_history(session, organization_id, mode="user_sync")
    vehicle_count = session.query(MotiveVehicleRecord).filter(MotiveVehicleRecord.organization_id == organization_id).count()
    user_count = session.query(MotiveDriverRecord).filter(MotiveDriverRecord.organization_id == organization_id, MotiveDriverRecord.source_endpoint == MOTIVE_USERS_ENDPOINT).count()
    if verification is None and vehicle_sync is None and user_sync is None:
        return {"vehicle_records_stored": vehicle_count, "user_records_stored": user_count, "driver_classification_certified": False}
    connection_status = "configured_unverified"
    if verification is not None:
        connection_status = "connected" if verification.status == "success" else verification.status
    latest_error = next((row for row in (verification, vehicle_sync, user_sync) if row and row.status != "success"), None)
    vehicle_counts = vehicle_sync.resource_counts if vehicle_sync and isinstance(vehicle_sync.resource_counts, dict) else {}
    user_counts = user_sync.resource_counts if user_sync and isinstance(user_sync.resource_counts, dict) else {}
    last_successful = _latest_completed_success(vehicle_sync, user_sync, verification)
    return {
        "connection_status": connection_status,
        "authorization_required": connection_status == "authorization_required",
        "last_verified_at": verification.completed_at.isoformat() if verification and verification.status == "success" and verification.completed_at else None,
        "last_successful_sync_at": last_successful.completed_at.isoformat() if last_successful and last_successful.completed_at else None,
        "last_error_code": latest_error.error_code if latest_error else None,
        "last_error_message_sanitized": latest_error.error_message_sanitized if latest_error else None,
        "records_read": verification.records_read if verification else 0,
        "last_vehicle_sync_at": vehicle_sync.completed_at.isoformat() if vehicle_sync and vehicle_sync.status == "success" and vehicle_sync.completed_at else None,
        "last_vehicle_sync_status": vehicle_sync.status if vehicle_sync else None,
        "vehicle_records_stored": vehicle_count,
        "last_vehicle_records_read": vehicle_sync.records_read if vehicle_sync else 0,
        "last_vehicle_pages_read": int(vehicle_counts.get("pages_read") or 0),
        "last_user_sync_at": user_sync.completed_at.isoformat() if user_sync and user_sync.status == "success" and user_sync.completed_at else None,
        "last_user_sync_status": user_sync.status if user_sync else None,
        "user_records_stored": user_count,
        "last_user_records_read": user_sync.records_read if user_sync else 0,
        "last_user_pages_read": int(user_counts.get("pages_read") or 0),
        "driver_classification_certified": False,
    }


def _latest_history(session: Session, organization_id: str, *, mode: str) -> MotiveSyncHistory | None:
    return (
        session.query(MotiveSyncHistory)
        .filter(MotiveSyncHistory.organization_id == organization_id, MotiveSyncHistory.provider == "motive", MotiveSyncHistory.mode == mode)
        .order_by(MotiveSyncHistory.started_at.desc(), MotiveSyncHistory.id.desc())
        .first()
    )


def _latest_completed_success(*rows: MotiveSyncHistory | None) -> MotiveSyncHistory | None:
    successes = [row for row in rows if row is not None and row.status == "success" and row.completed_at is not None]
    return max(successes, key=lambda row: row.completed_at) if successes else None


def _upsert_vehicles(session: Session, vehicles: list[MotiveVehicle]) -> dict[str, int]:
    counts = {"records_inserted": 0, "records_updated": 0, "records_unchanged": 0, "records_upserted": 0}
    now = datetime.now(timezone.utc)
    for vehicle in vehicles:
        existing = (
            session.query(MotiveVehicleRecord)
            .filter(
                MotiveVehicleRecord.organization_id == vehicle.organization_id,
                MotiveVehicleRecord.provider_vehicle_id == vehicle.provider_vehicle_id,
            )
            .one_or_none()
        )
        values = {
            "organization_slug": vehicle.organization_slug,
            "provider": "motive",
            "source_endpoint": vehicle.source_endpoint,
            "unit_number": vehicle.unit_number,
            "vin": vehicle.vin,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "license_plate": vehicle.license_plate,
            "status": vehicle.status,
            "observed_at": vehicle.observed_at,
            "provider_payload_metadata": vehicle.metadata,
        }
        if existing is None:
            session.add(MotiveVehicleRecord(organization_id=vehicle.organization_id, provider_vehicle_id=vehicle.provider_vehicle_id, **values))
            counts["records_inserted"] += 1
            continue
        changed = any(getattr(existing, key) != value for key, value in values.items())
        if changed:
            for key, value in values.items():
                setattr(existing, key, value)
            existing.updated_at = now
            counts["records_updated"] += 1
        else:
            counts["records_unchanged"] += 1
    counts["records_upserted"] = counts["records_inserted"] + counts["records_updated"]
    return counts


def _upsert_users(session: Session, users: list[MotiveDriver]) -> dict[str, int]:
    counts = {"records_inserted": 0, "records_updated": 0, "records_unchanged": 0, "records_upserted": 0}
    now = datetime.now(timezone.utc)
    for user in users:
        provider_user_id = user.provider_driver_id
        if not provider_user_id:
            raise MotiveConnectorError("Motive user did not include a provider user id", status=ConnectorStatus.FAILED, code="provider_contract_error")
        existing = (
            session.query(MotiveDriverRecord)
            .filter(
                MotiveDriverRecord.organization_id == user.organization_id,
                MotiveDriverRecord.provider_driver_id == provider_user_id,
            )
            .one_or_none()
        )
        values = {
            "organization_slug": user.organization_slug,
            "provider": "motive",
            "source_endpoint": user.source_endpoint,
            "name": user.name,
            "email": user.email,
            "status": user.status,
            "observed_at": user.observed_at,
            "provider_payload_metadata": user.metadata,
        }
        if existing is None:
            session.add(MotiveDriverRecord(organization_id=user.organization_id, provider_driver_id=provider_user_id, **values))
            counts["records_inserted"] += 1
            continue
        changed = any(getattr(existing, key) != value for key, value in values.items())
        if changed:
            for key, value in values.items():
                setattr(existing, key, value)
            existing.updated_at = now
            counts["records_updated"] += 1
        else:
            counts["records_unchanged"] += 1
    counts["records_upserted"] = counts["records_inserted"] + counts["records_updated"]
    return counts


def _resource_checkpoint(session: Session, organization_id: str, provider_resource: str) -> MotiveSyncCheckpoint | None:
    return (
        session.query(MotiveSyncCheckpoint)
        .filter(MotiveSyncCheckpoint.organization_id == organization_id, MotiveSyncCheckpoint.provider_resource == provider_resource)
        .one_or_none()
    )


def _ensure_resource_checkpoint(session: Session, organization: Organization, provider_resource: str) -> MotiveSyncCheckpoint:
    checkpoint = _resource_checkpoint(session, organization.id, provider_resource)
    if checkpoint is None:
        checkpoint = MotiveSyncCheckpoint(organization_id=organization.id, organization_slug=organization.slug, provider_resource=provider_resource, provider="motive")
        session.add(checkpoint)
    return checkpoint


def _vehicle_checkpoint(session: Session, organization_id: str) -> MotiveSyncCheckpoint | None:
    return _resource_checkpoint(session, organization_id, "vehicles")


def _ensure_vehicle_checkpoint(session: Session, organization: Organization) -> MotiveSyncCheckpoint:
    return _ensure_resource_checkpoint(session, organization, "vehicles")


def _checkpoint_snapshot(checkpoint: MotiveSyncCheckpoint | None) -> dict[str, Any]:
    if checkpoint is None:
        return {}
    return {
        "page_number": checkpoint.page_number,
        "cursor": checkpoint.cursor,
        "updated_after_watermark": checkpoint.updated_after_watermark,
        "last_successful_position": checkpoint.last_successful_position or {},
        "last_successful_sync_at": checkpoint.last_successful_sync_at.isoformat() if checkpoint.last_successful_sync_at else None,
    }


def _create_running_history(
    session: Session,
    organization: Organization,
    *,
    run_id: str,
    provider_resource: str,
    mode: str,
    checkpoint_before: dict[str, Any],
    started_at: datetime,
) -> MotiveSyncHistory:
    history = MotiveSyncHistory(
        organization_id=organization.id,
        organization_slug=organization.slug,
        provider="motive",
        provider_resource=provider_resource,
        mode=mode,
        status="running",
        run_id=run_id,
        started_at=started_at,
        checkpoint_before=checkpoint_before,
        checkpoint_after=checkpoint_before,
        resource_counts={},
    )
    session.add(history)
    session.commit()
    return history


def _checkpoint_after(result: dict[str, Any], completed_at: datetime) -> dict[str, Any]:
    return {
        "page_number": result["pages_read"],
        "records_read": result["records_read"],
        "pagination_total": result.get("pagination_total"),
        "completed_at": completed_at.isoformat(),
    }


def _mark_checkpoint_success(checkpoint: MotiveSyncCheckpoint, checkpoint_after: dict[str, Any], completed_at: datetime) -> None:
    checkpoint.page_number = int(checkpoint_after.get("page_number") or 0)
    checkpoint.last_successful_position = checkpoint_after
    checkpoint.checkpoint_status = "success"
    checkpoint.last_successful_sync_at = completed_at
    checkpoint.updated_at = completed_at


def _mark_history_success(
    history: MotiveSyncHistory,
    *,
    result: dict[str, Any],
    counts: dict[str, int],
    checkpoint_after: dict[str, Any],
    completed_at: datetime,
    resource: str,
) -> None:
    history.status = "success"
    history.completed_at = completed_at
    history.records_read = int(result["records_read"] or 0)
    history.records_written = counts["records_upserted"]
    history.checkpoint_after = checkpoint_after
    history.resource_counts = {
        resource: history.records_read,
        "pages_read": int(result["pages_read"] or 0),
        **counts,
    }


def _sync_response(
    *,
    result: dict[str, Any],
    counts: dict[str, int],
    history: MotiveSyncHistory,
    resource: str,
    certified_field: str,
) -> dict[str, Any]:
    return {
        "status": "success",
        "resource": resource,
        "pages_read": int(result["pages_read"] or 0),
        "records_read": int(result["records_read"] or 0),
        "records_inserted": counts["records_inserted"],
        "records_updated": counts["records_updated"],
        "records_unchanged": counts["records_unchanged"],
        "records_upserted": counts["records_upserted"],
        "completed_at": history.completed_at.isoformat() if history.completed_at else None,
        "error_code": None,
        "production_certified": False,
        certified_field: True,
        "secrets_exposed": False,
        "run_id": history.run_id,
    }


def _mark_history_failure(session: Session, history: MotiveSyncHistory, exc: MotiveConnectorError, *, checkpoint_before: dict[str, Any], resource: str = "vehicles") -> None:
    history.status = exc.status.value
    history.completed_at = datetime.now(timezone.utc)
    history.error_code = exc.code
    history.error_message_sanitized = str(exc)
    history.records_read = 0
    history.records_written = 0
    history.resource_counts = {resource: 0}
    history.checkpoint_after = checkpoint_before
    session.commit()


def _mark_persistence_failure(session: Session, *, run_id: str, checkpoint_before: dict[str, Any], resource: str, message: str) -> None:
    try:
        session.rollback()
        history = session.query(MotiveSyncHistory).filter(MotiveSyncHistory.run_id == run_id).one_or_none()
        if history is None:
            return
        history.status = "failed"
        history.completed_at = datetime.now(timezone.utc)
        history.error_code = _DATABASE_PERSISTENCE_ERROR_CODE
        history.error_message_sanitized = message
        history.records_written = 0
        history.resource_counts = {resource: 0}
        history.checkpoint_after = checkpoint_before
        session.commit()
    except SQLAlchemyError:
        session.rollback()


def _mark_vehicle_persistence_failure(session: Session, *, run_id: str, checkpoint_before: dict[str, Any]) -> None:
    _mark_persistence_failure(session, run_id=run_id, checkpoint_before=checkpoint_before, resource="vehicles", message=_DATABASE_VEHICLE_PERSISTENCE_ERROR_MESSAGE)


def _persistence_http_exception(resource: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"status": "failed", "resource": resource, "error_code": _DATABASE_PERSISTENCE_ERROR_CODE, "message": message},
    )


def _http_status(error: MotiveConnectorError) -> int:
    if error.status.value == "authorization_required":
        return status.HTTP_401_UNAUTHORIZED
    if error.status.value == "rate_limited":
        return status.HTTP_429_TOO_MANY_REQUESTS
    if error.code == "provider_timeout":
        return status.HTTP_504_GATEWAY_TIMEOUT
    if error.status.value == "not_configured":
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if error.code == "provider_contract_error":
        return status.HTTP_502_BAD_GATEWAY
    return status.HTTP_502_BAD_GATEWAY
