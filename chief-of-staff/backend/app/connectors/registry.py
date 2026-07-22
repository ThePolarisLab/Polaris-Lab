"""Thread-safe in-process registry for Polaris connectors."""

from threading import RLock

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth


class ConnectorRegistry:
    """Register, discover, and inspect connector instances by unique name."""

    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}
        self._lock = RLock()

    def register(self, connector: BaseConnector, *, replace: bool = False) -> None:
        key = self._normalize(connector.name)
        with self._lock:
            if key in self._connectors and not replace:
                raise ValueError(f"Connector '{connector.name}' is already registered")
            self._connectors[key] = connector

    def unregister(self, name: str) -> BaseConnector:
        key = self._normalize(name)
        with self._lock:
            try:
                return self._connectors.pop(key)
            except KeyError as exc:
                raise KeyError(f"Connector '{name}' is not registered") from exc

    def get(self, name: str) -> BaseConnector:
        key = self._normalize(name)
        with self._lock:
            try:
                return self._connectors[key]
            except KeyError as exc:
                raise KeyError(f"Connector '{name}' is not registered") from exc

    def list(self) -> tuple[BaseConnector, ...]:
        with self._lock:
            return tuple(self._connectors[key] for key in sorted(self._connectors))

    def health(self) -> tuple[ConnectorHealth, ...]:
        return tuple(connector.health() for connector in self.list())

    def clear(self) -> None:
        """Remove every connector. Intended primarily for tests and app shutdown."""
        with self._lock:
            self._connectors.clear()

    @staticmethod
    def _normalize(name: str) -> str:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Connector name cannot be empty")
        return normalized


connector_registry = ConnectorRegistry()
