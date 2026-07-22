"""Base contract implemented by all Polaris connectors."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from app.connectors.models import ConnectorHealth, SyncResult


class BaseConnector(ABC):
    """Stable lifecycle and synchronization contract for external systems."""

    def __init__(self, name: str, config: Mapping[str, Any] | None = None) -> None:
        self._name = name
        self._config = dict(config or {})

    @property
    def name(self) -> str:
        """Return the unique registry name for this connector."""
        return self._name

    @property
    def config(self) -> Mapping[str, Any]:
        """Return a read-only view of connector configuration values."""
        return self._config.copy()

    def initialize(self) -> None:
        """Validate configuration and prepare local connector resources."""
        self.validate_configuration()

    @abstractmethod
    def validate_configuration(self) -> None:
        """Raise a descriptive exception when required configuration is invalid."""

    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the external system without exposing credentials."""

    @abstractmethod
    def health(self) -> ConnectorHealth:
        """Return the connector's current normalized health state."""

    @abstractmethod
    def discover(self) -> Sequence[str]:
        """Return resource types or capabilities available from the connector."""

    @abstractmethod
    def sync(self) -> SyncResult:
        """Synchronize external data into Polaris and return a normalized result."""

    def disconnect(self) -> None:
        """Release connector resources. Stateless connectors may keep this no-op."""

    def capabilities(self) -> Sequence[str]:
        """Return capabilities advertised by the connector."""
        return self.discover()
