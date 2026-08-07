"""Authenticated Motive connector APIs for Company API Key verification and vehicle ingestion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.motive import (
    MOTIVE_AUTHENTICATION_METHOD,
    MOTIVE_CONFIRMED_ENDPOINTS,
    MOTIVE_CREDENTIAL_SOURCE,
    MOTIVE_VEHICLES_ENDPOINT,
    MOTIVE_VEHICLES_PER_PAGE,
    MOTIVE_VERIFICATION_ENDPOINT,
    MOTIVE_VERIFICATION_PARAMS,
    MotiveConnector,
    MotiveConnectorError,
)
from app.connectors.motive_contracts import MotiveVehicle
from app.database.database import SessionLocal
from app.models.motive import MotiveSyncCheckpoint, MotiveSyncHistory, MotiveVehicleRecord
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/motive", tags=["motive"])


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


@router.post("/sync/vehicles")
def sync_motive_vehicles(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one manual read-only vehicle ingestion for the active organization."""
    organization = _organization(session, principal.organization_id)
    checkpoint = _vehicle_checkpoint(session, principal.organization_id)
    checkpoint_before = _checkpoint_snapshot(checkpoint)
    started_at = datetime.now(timezone.utc)
    run_id = f"motive-vehicles-{uuid4()}"
    history = MotiveSyncHistory(
        organization_id=principal.organization_id,
        organization_slug=organization.slug,
        provider="motive",
        provider_resource="vehicles",
        mode="vehicle_sync",
        status="running",
        run_id=run_id,
        started_at=started_at,
        checkpoint_before=checkpoint_before,
        checkpoint_after=checkpoint_before,
        resource_counts={},
    )
    session.add(history)
    session.commit()
    try:
        result = _connector(principal.organization_id).list_vehicles(organization_id=principal.organization_id, organization_slug=organization.slug)
        counts = _upsert_vehicles(session, result["vehicles"])
        completed_at = datetime.now(timezone.utc)
        checkpoint_after = {
            "page_number": result["pages_read"],
            "records_read": result["records_read"],
            "pagination_total": result.get("pagination_total"),
            "completed_at": completed_at.isoformat(),
        }
        checkpoint = _ensure_vehicle_checkpoint(session, organization)
        checkpoint.page_number = int(result["pages_read"] or 0)
        checkpoint.last_successful_position = checkpoint_after
        checkpoint.checkpoint_status = "success"
        checkpoint.last_successful_sync_at = completed_at
        checkpoint.updated_at = completed_at
        history.status = "success"
        history.completed_at = completed_at
        history.records_read = int(result["records_read"] or 0)
        history.records_written = counts["records_upserted"]
        history.checkpoint_after = checkpoint_after
        history.resource_counts = {
            "vehicles": history.records_read,
            "pages_read": int(result["pages_read"] or 0),
            **counts,
        }
        session.commit()
    except MotiveConnectorError as exc:
        session.rollback()
        history = session.query(MotiveSyncHistory).filter(MotiveSyncHistory.run_id == run_id).one()
        _mark_history_failure(session, history, exc, checkpoint_before=checkpoint_before)
        raise HTTPException(status_code=_http_status(exc), detail={"status": exc.status.value, "resource": "vehicles", "error_code": exc.code, "message": str(exc)}) from exc
    response = {
        "status": "success",
        "resource": "vehicles",
        "pages_read": int(result["pages_read"] or 0),
        "records_read": int(result["records_read"] or 0),
        "records_inserted": counts["records_inserted"],
        "records_updated": counts["records_updated"],
        "records_unchanged": counts["records_unchanged"],
        "records_upserted": counts["records_upserted"],
        "completed_at": history.completed_at.isoformat() if history.completed_at else None,
        "error_code": None,
        "production_certified": False,
        "vehicle_ingestion_certified": True,
        "secrets_exposed": False,
        "run_id": run_id,
    }
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
        "driver_user_pagination": {"endpoint": "/v1/users", "per_page_max": 100, "page_no": "one_based", "total_field": "pagination.total"},
        "verification_endpoint": MOTIVE_VERIFICATION_ENDPOINT,
        "verification_request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": dict(MOTIVE_VERIFICATION_PARAMS), "authentication": "company_api_key_header"},
        "vehicle_sync": {"method": "GET", "path": MOTIVE_VEHICLES_ENDPOINT, "params": {"per_page": MOTIVE_VEHICLES_PER_PAGE, "page_no": "one_based"}, "manual_route": "/api/v1/motive/sync/vehicles"},
        "oauth_runtime_enabled": False,
        "broad_sync_enabled": False,
        "production_certified": False,
        "vehicle_ingestion_certified_only_after_successful_manual_sync": True,
        "secrets_exposed": False,
    }


def _organization(session: Session, organization_id: str) -> Organization:
    organization = session.query(Organization).filter(Organization.id == organization_id).one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


def _latest_motive_status(session: Session, organization_id: str) -> dict[str, Any] | None:
    verification = (
        session.query(MotiveSyncHistory)
        .filter(MotiveSyncHistory.organization_id == organization_id, MotiveSyncHistory.provider == "motive", MotiveSyncHistory.mode == "verification")
        .order_by(MotiveSyncHistory.started_at.desc(), MotiveSyncHistory.id.desc())
        .first()
    )
    vehicle_sync = (
        session.query(MotiveSyncHistory)
        .filter(MotiveSyncHistory.organization_id == organization_id, MotiveSyncHistory.provider == "motive", MotiveSyncHistory.mode == "vehicle_sync")
        .order_by(MotiveSyncHistory.started_at.desc(), MotiveSyncHistory.id.desc())
        .first()
    )
    vehicle_count = session.query(MotiveVehicleRecord).filter(MotiveVehicleRecord.organization_id == organization_id).count()
    if verification is None and vehicle_sync is None:
        return {"vehicle_records_stored": vehicle_count}
    connection_status = "configured_unverified"
    if verification is not None:
        connection_status = "connected" if verification.status == "success" else verification.status
    latest_error = verification if verification and verification.status != "success" else vehicle_sync if vehicle_sync and vehicle_sync.status != "success" else None
    vehicle_counts = vehicle_sync.resource_counts if vehicle_sync and isinstance(vehicle_sync.resource_counts, dict) else {}
    return {
        "connection_status": connection_status,
        "authorization_required": connection_status == "authorization_required",
        "last_verified_at": verification.completed_at.isoformat() if verification and verification.status == "success" and verification.completed_at else None,
        "last_successful_sync_at": vehicle_sync.completed_at.isoformat() if vehicle_sync and vehicle_sync.status == "success" and vehicle_sync.completed_at else (verification.completed_at.isoformat() if verification and verification.status == "success" and verification.completed_at else None),
        "last_error_code": latest_error.error_code if latest_error else None,
        "last_error_message_sanitized": latest_error.error_message_sanitized if latest_error else None,
        "records_read": verification.records_read if verification else 0,
        "last_vehicle_sync_at": vehicle_sync.completed_at.isoformat() if vehicle_sync and vehicle_sync.status == "success" and vehicle_sync.completed_at else None,
        "last_vehicle_sync_status": vehicle_sync.status if vehicle_sync else None,
        "vehicle_records_stored": vehicle_count,
        "last_vehicle_records_read": vehicle_sync.records_read if vehicle_sync else 0,
        "last_vehicle_pages_read": int(vehicle_counts.get("pages_read") or 0),
    }


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


def _vehicle_checkpoint(session: Session, organization_id: str) -> MotiveSyncCheckpoint | None:
    return (
        session.query(MotiveSyncCheckpoint)
        .filter(MotiveSyncCheckpoint.organization_id == organization_id, MotiveSyncCheckpoint.provider_resource == "vehicles")
        .one_or_none()
    )


def _ensure_vehicle_checkpoint(session: Session, organization: Organization) -> MotiveSyncCheckpoint:
    checkpoint = _vehicle_checkpoint(session, organization.id)
    if checkpoint is None:
        checkpoint = MotiveSyncCheckpoint(organization_id=organization.id, organization_slug=organization.slug, provider_resource="vehicles", provider="motive")
        session.add(checkpoint)
    return checkpoint


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


def _mark_history_failure(session: Session, history: MotiveSyncHistory, exc: MotiveConnectorError, *, checkpoint_before: dict[str, Any]) -> None:
    history.status = exc.status.value
    history.completed_at = datetime.now(timezone.utc)
    history.error_code = exc.code
    history.error_message_sanitized = str(exc)
    history.records_read = 0
    history.records_written = 0
    history.resource_counts = {"vehicles": 0}
    history.checkpoint_after = checkpoint_before
    session.commit()


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
