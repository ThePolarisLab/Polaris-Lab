"""Builder-facing Connector SDK endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.connectors.models import ConnectorHealth
from app.connectors.registry import connector_registry

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorHealth])
def list_connectors() -> list[ConnectorHealth]:
    """Return normalized health for every registered connector."""
    return list(connector_registry.health())


@router.get("/{name}", response_model=ConnectorHealth)
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
