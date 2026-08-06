"""Authenticated Motive connector APIs for OAuth foundation verification."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.connectors.motive import (
    MOTIVE_AUTHORIZATION_URL,
    MOTIVE_OAUTH_SCOPES,
    MOTIVE_TOKEN_URL,
    MOTIVE_VERIFICATION_ENDPOINT,
    MotiveConnector,
    MotiveConnectorError,
    MotiveOAuthService,
)
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


def _frontend_base_url() -> str:
    base_url = os.getenv("POLARIS_FRONTEND_URL")
    if not base_url:
        raise MotiveConnectorError("Motive frontend return URL is not configured", status=ConnectorStatus.NOT_CONFIGURED, code="frontend_url_missing")  # type: ignore[name-defined]
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or base_url != base_url.strip():
        raise MotiveConnectorError("Motive frontend return URL is invalid", status=ConnectorStatus.NOT_CONFIGURED, code="frontend_url_invalid")  # type: ignore[name-defined]
    return base_url.rstrip("/")


def _frontend_return_url(result: str) -> str:
    return f"{_frontend_base_url()}/#executive/connectors?motive={quote(result, safe='')}"


@router.get("/status")
def motive_status(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    connector = _connector(principal.organization_id)
    return {"health": connector.health().model_dump(mode="json"), "status": connector.safe_status()}


@router.get("/connect")
def motive_connect(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Return a Motive authorization URL after Polaris auth and org checks pass."""
    organization = _organization(session, principal.organization_id)
    try:
        _frontend_base_url()
        return MotiveOAuthService().create_authorization_url(
            organization_id=principal.organization_id,
            identity_id=principal.identity_id,
            organization_slug=organization.slug,
        )
    except MotiveConnectorError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error_code": exc.code, "message": str(exc)}) from exc


@router.get("/oauth/callback")
def motive_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Public Motive callback protected by one-use organization-scoped OAuth state."""
    if error:
        return RedirectResponse(_frontend_return_url("denied"), status_code=status.HTTP_303_SEE_OTHER)
    if not code or not state:
        return RedirectResponse(_frontend_return_url("error"), status_code=status.HTTP_303_SEE_OTHER)
    try:
        MotiveOAuthService().complete_authorization(code=code, state=state)
    except MotiveConnectorError:
        return RedirectResponse(_frontend_return_url("error"), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(_frontend_return_url("connected_unverified"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/verify")
def verify_motive_connection(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
    session: Session = Depends(_db),
) -> dict[str, Any]:
    """Run one narrow read-only Motive OAuth bearer verification request for the active organization."""
    organization = _organization(session, principal.organization_id)
    started_at = datetime.now(timezone.utc)
    run_id = f"motive-verify-{uuid4()}"
    history = MotiveSyncHistory(
        organization_id=principal.organization_id,
        organization_slug=organization.slug,
        provider="motive",
        provider_resource="companies",
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
        history.resource_counts = {"companies": 0}
        history.checkpoint_after = history.checkpoint_before
        session.commit()
        raise HTTPException(status_code=_http_status(exc), detail={"status": exc.status.value, "error_code": exc.code, "message": str(exc)}) from exc
    history.status = "success"
    history.completed_at = datetime.now(timezone.utc)
    history.records_read = int(result.get("records_read") or 0)
    history.records_written = 0
    history.resource_counts = {"companies": history.records_read}
    history.checkpoint_after = history.checkpoint_before
    session.commit()
    return {**result, "run_id": run_id}


@router.post("/disconnect")
def disconnect_motive(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE))) -> dict[str, Any]:
    _connector(principal.organization_id).disconnect()
    return {
        "disconnected": True,
        "organization_id": principal.organization_id,
        "remote_revocation_performed": False,
        "remote_revocation_reason": "Motive token revocation is not implemented because no official revocation contract has been verified for this PR.",
        "secrets_exposed": False,
    }


@router.get("/verification-contract")
def motive_verification_contract(principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ))) -> dict[str, Any]:
    return {
        "provider": "motive",
        "authentication_method": "oauth2",
        "authorization_endpoint": MOTIVE_AUTHORIZATION_URL,
        "token_endpoint": MOTIVE_TOKEN_URL,
        "redirect_uri_environment_variable": "MOTIVE_REDIRECT_URI",
        "frontend_url_environment_variable": "POLARIS_FRONTEND_URL",
        "callback_route": "/api/v1/motive/oauth/callback",
        "requested_scopes": list(MOTIVE_OAUTH_SCOPES),
        "verification_endpoint": MOTIVE_VERIFICATION_ENDPOINT,
        "verification_request": {"method": "GET", "path": MOTIVE_VERIFICATION_ENDPOINT, "params": {}, "authorization": "Bearer access token"},
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
    if error.status.value == "not_configured":
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_502_BAD_GATEWAY
