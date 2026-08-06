"""Authenticated Motive connector APIs for API-key foundation verification."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.motive import MOTIVE_VERIFICATION_ENDPOINT, MOTIVE_VERIFICATION_PARAMS, MotiveConnector, MotiveConnectorError
from app.connectors.motive_credentials import MotiveCredentialStore
from app.database.database import SessionLocal
from app.models.motive import MotiveSyncHistory
from app.organizations.models import Organization
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/motive", tags=["motive"])


def _db() -> Session:
    with SessionLocal() as session:
        yield session


def _connector(organization_id: str) -> MotiveConnector:
    return MotiveConnector(credential_store=MotiveCredentialStore(organization_id))


@router.get("/status")
def motive_status(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    connector = _connector(principal.organization_id)
    return {"health": connector.health().model_dump(mode="json"), "status": connector.safe_status()}


@router.post("/credentials/from-environment")
def configure_motive_from_environment(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Install or rotate the active organization's Motive API key from MOTIVE_API_KEY only."""
    api_key = os.getenv("MOTIVE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MOTIVE_API_KEY is not configured")
    organization = _organization(session, principal.organization_id)
    environment_mode = os.getenv("POLARIS_MOTIVE_ENVIRONMENT_MODE", "test").strip().lower() or "test"
    MotiveCredentialStore(principal.organization_id).save_api_key(
        organization_slug=organization.slug,
        api_key=api_key,
        environment_mode=environment_mode,
    )
    metadata = MotiveCredentialStore(principal.organization_id).metadata(environment_mode=environment_mode)
    return {"configured": True, "status": metadata}


@router.post("/verify")
def verify_motive_connection(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one small read-only Motive API-key verification request for the active organization."""
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
    _connector(principal.organization_id).disconnect()
    return {"disconnected": True, "organization_id": principal.organization_id, "secrets_exposed": False}


@router.get("/verification-contract")
def motive_verification_contract(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    return {
        "provider": "motive",
        "authentication_method": "api_key",
        "header": "X-API-Key",
        "endpoint": MOTIVE_VERIFICATION_ENDPOINT,
        "request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": MOTIVE_VERIFICATION_PARAMS},
        "broad_sync_enabled": False,
        "production_certified": False,
        "secrets_exposed": False,
    }


def _organization(session: Session, organization_id: str) -> Organization:
    organization = session.query(Organization).filter(Organization.id == organization_id).one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


def _http_status(error: MotiveConnectorError) -> int:
    if error.status.value == "authorization_required":
        return status.HTTP_401_UNAUTHORIZED
    if error.status.value == "rate_limited":
        return status.HTTP_429_TOO_MANY_REQUESTS
    if error.code == "timeout":
        return status.HTTP_504_GATEWAY_TIMEOUT
    return status.HTTP_502_BAD_GATEWAY
