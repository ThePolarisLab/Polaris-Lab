"""Authenticated Motive connector APIs for Company API Key verification."""

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
    MOTIVE_VERIFICATION_ENDPOINT,
    MOTIVE_VERIFICATION_PARAMS,
    MotiveConnector,
    MotiveConnectorError,
)
from app.database.database import SessionLocal
from app.models.motive import MotiveSyncHistory
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
        history.status = exc.status.value
        history.completed_at = datetime.now(timezone.utc)
        history.error_code = exc.code
        history.error_message_sanitized = str(exc)
        history.records_read = 0
        history.records_written = 0
        history.resource_counts = {"vehicles": 0}
        history.checkpoint_after = history.checkpoint_before
        session.commit()
        raise HTTPException(status_code=_http_status(exc), detail={"status": exc.status.value, "error_code": exc.code, "message": str(exc)}) from exc
    history.status = "success"
    history.completed_at = datetime.now(timezone.utc)
    history.records_read = int(result.get("records_read") or 0)
    history.records_written = 0
    history.resource_counts = {"vehicles": history.records_read}
    history.checkpoint_after = history.checkpoint_before
    session.commit()
    return {**result, "run_id": run_id}


@router.post("/disconnect")
def disconnect_motive(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE))) -> dict[str, Any]:
    return {
        "disconnected": False,
        "organization_id": principal.organization_id,
        "configuration_managed_by": "administrator_environment",
        "message": "Motive Company API Key is managed in backend environment configuration. Remove MOTIVE_API_KEY to disconnect.",
        "secrets_exposed": False,
    }


@router.get("/verification-contract")
def motive_verification_contract(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    return {
        "provider": "motive",
        "authentication_method": MOTIVE_AUTHENTICATION_METHOD,
        "credential_source": MOTIVE_CREDENTIAL_SOURCE,
        "credential_environment_variable": "MOTIVE_API_KEY",
        "request_header": "X-API-Key",
        "confirmed_endpoints": list(MOTIVE_CONFIRMED_ENDPOINTS),
        "driver_user_pagination": {"endpoint": "/v1/users", "per_page_max": 100, "page_no": "one_based", "total_field": "pagination.total"},
        "verification_endpoint": MOTIVE_VERIFICATION_ENDPOINT,
        "verification_request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": dict(MOTIVE_VERIFICATION_PARAMS), "authentication": "X-API-Key"},
        "oauth_runtime_enabled": False,
        "broad_sync_enabled": False,
        "production_certified": False,
        "secrets_exposed": False,
    }


def _organization(session: Session, organization_id: str) -> Organization:
    organization = session.query(Organization).filter(Organization.id == organization_id).one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


def _latest_motive_status(session: Session, organization_id: str) -> dict[str, Any] | None:
    history = (
        session.query(MotiveSyncHistory)
        .filter(MotiveSyncHistory.organization_id == organization_id, MotiveSyncHistory.provider == "motive", MotiveSyncHistory.mode == "verification")
        .order_by(MotiveSyncHistory.started_at.desc(), MotiveSyncHistory.id.desc())
        .first()
    )
    if history is None:
        return None
    connection_status = "connected" if history.status == "success" else history.status
    return {
        "connection_status": connection_status,
        "authorization_required": connection_status == "authorization_required",
        "last_verified_at": history.completed_at.isoformat() if history.status == "success" and history.completed_at else None,
        "last_successful_sync_at": history.completed_at.isoformat() if history.status == "success" and history.completed_at else None,
        "last_error_code": history.error_code,
        "last_error_message_sanitized": history.error_message_sanitized,
        "records_read": history.records_read,
    }


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
