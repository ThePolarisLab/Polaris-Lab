"""Builder-facing Connector SDK endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.connectors.models import ConnectorHealth, SyncResult
from app.connectors.registry import connector_registry
from app.security.dependencies import require_permission
from app.security.models import Permission

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])

connector_read = Depends(require_permission(Permission.CONNECTOR_READ))
connector_manage = Depends(require_permission(Permission.CONNECTOR_MANAGE))


@router.get("", response_model=list[ConnectorHealth], dependencies=[connector_read])
def list_connectors() -> list[ConnectorHealth]:
    """Return normalized health for every registered connector."""
    return list(connector_registry.health())


@router.get("/{name}", response_model=ConnectorHealth, dependencies=[connector_read])
def get_connector(name: str) -> ConnectorHealth:
    """Return normalized health for one registered connector."""
    try:
        connector = connector_registry.get(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return connector.health()


@router.post("/{name}/sync", response_model=SyncResult, dependencies=[connector_manage])
def sync_connector(name: str) -> SyncResult:
    """Run one explicit connector synchronization cycle."""
    try:
        connector = connector_registry.get(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return connector.sync()
