"""Builder-facing Connector SDK endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, SyncResult
from app.connectors.outlook import OutlookConnector
from app.connectors.outlook_credentials import OutlookCredentialStore
from app.connectors.quickbooks import QuickBooksConnector
from app.connectors.quickbooks_credentials import QuickBooksCredentialStore
from app.connectors.registry import connector_registry
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


def _tenant_connector(connector: BaseConnector, principal: AuthenticatedPrincipal) -> BaseConnector:
    if connector.name.lower() == "quickbooks":
        return QuickBooksConnector(credential_store=QuickBooksCredentialStore(principal.organization_id))
    if connector.name.lower() == "outlook":
        return OutlookConnector(credential_store=OutlookCredentialStore(principal.organization_id))
    return connector


@router.get("", response_model=list[ConnectorHealth])
def list_connectors(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
) -> list[ConnectorHealth]:
    """Return normalized health for every registered connector in the active tenant context."""
    return [_tenant_connector(connector, principal).health() for connector in connector_registry.list()]


@router.get("/{name}", response_model=ConnectorHealth)
def get_connector(
    name: str,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_READ)),
) -> ConnectorHealth:
    """Return normalized health for one registered connector."""
    try:
        connector = connector_registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _tenant_connector(connector, principal).health()


@router.post("/{name}/sync", response_model=SyncResult)
def sync_connector(
    name: str,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.CONNECTOR_WRITE)),
) -> SyncResult:
    """Run one explicit connector synchronization cycle."""
    try:
        connector = connector_registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _tenant_connector(connector, principal).sync()
