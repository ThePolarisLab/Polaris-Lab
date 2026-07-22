"""Polaris connector SDK.

Connectors expose external systems through a consistent lifecycle, health,
and synchronization contract.
"""

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.registry import ConnectorRegistry, connector_registry

__all__ = [
    "BaseConnector",
    "ConnectorHealth",
    "ConnectorRegistry",
    "ConnectorStatus",
    "SyncResult",
    "connector_registry",
]
