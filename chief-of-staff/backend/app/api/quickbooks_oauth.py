"""Polaris-owned QuickBooks OAuth endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.connectors.quickbooks import QuickBooksConnector
from app.connectors.quickbooks_credentials import QuickBooksCredentialStore
from app.connectors.quickbooks_oauth import QuickBooksOAuthError, QuickBooksOAuthService
from app.core.config import settings
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/connectors/quickbooks/oauth", tags=["quickbooks-oauth"])


def _connector_manager(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_MANAGE)),
) -> AuthenticatedPrincipal:
    return principal


@router.get("/authorize")
def authorize_quickbooks(
    principal: AuthenticatedPrincipal = Depends(_connector_manager),
) -> RedirectResponse:
    """Start the dedicated Polaris QuickBooks authorization flow."""
    try:
        return RedirectResponse(
            QuickBooksOAuthService().authorization_url(
                organization_id=principal.organization_id,
                identity_id=principal.identity_id,
                organization_slug=settings.organization_slug,
            ),
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )
    except QuickBooksOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/callback")
def quickbooks_callback(
    code: str | None = Query(default=None),
    realmId: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Validate Intuit callback, exchange the code, and store tokens in Polaris."""
    frontend_url = os.getenv("POLARIS_FRONTEND_URL", "http://localhost:5173")
    if error:
        return RedirectResponse(
            f"{frontend_url}/executive/connectors?quickbooks=denied",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if not code or not realmId or not state:
        raise HTTPException(
            status_code=400, detail="QuickBooks callback is missing required parameters"
        )
    try:
        context = QuickBooksOAuthService().complete_authorization(
            code=code, realm_id=realmId, state=state
        )
        store = QuickBooksCredentialStore(context.organization_slug)
        health = QuickBooksConnector(credential_store=store).health()
        if health.status.value != "healthy":
            store.delete()
            raise QuickBooksOAuthError(
                health.message or "QuickBooks company verification failed"
            )
    except QuickBooksOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        f"{frontend_url}/executive/connectors?quickbooks=connected",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.delete("/connection")
def disconnect_quickbooks(
    principal: AuthenticatedPrincipal = Depends(_connector_manager),
) -> dict[str, bool]:
    """Remove the stored QuickBooks authorization for the active organization."""
    QuickBooksCredentialStore(settings.organization_slug).delete()
    return {"disconnected": True, "organization_id": principal.organization_id}
