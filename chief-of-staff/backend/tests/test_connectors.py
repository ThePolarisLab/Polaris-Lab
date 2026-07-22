from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorHealth, ConnectorStatus, SyncResult
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.main import app


class ExampleConnector(BaseConnector):
    def __init__(self, name: str = "example") -> None:
        super().__init__(name)

    def validate_configuration(self) -> None:
        return None

    def authenticate(self) -> None:
        return None

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(name=self.name, status=ConnectorStatus.HEALTHY)

    def discover(self) -> tuple[str, ...]:
        return ("examples",)

    def sync(self) -> SyncResult:
        now = datetime.now(timezone.utc)
        return SyncResult(connector=self.name, started_at=now, completed_at=now)


def test_registry_register_get_list_and_unregister() -> None:
    registry = ConnectorRegistry()
    connector = ExampleConnector()

    registry.register(connector)

    assert registry.get("EXAMPLE") is connector
    assert registry.list() == (connector,)
    assert registry.health()[0].status == ConnectorStatus.HEALTHY
    assert registry.unregister("example") is connector


def test_registry_rejects_duplicate_connector_names() -> None:
    registry = ConnectorRegistry()
    registry.register(ExampleConnector())

    try:
        registry.register(ExampleConnector(" Example "))
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Expected duplicate registration to fail")


def test_connector_health_api() -> None:
    connector_registry.clear()
    connector_registry.register(ExampleConnector())
    client = TestClient(app)

    response = client.get("/api/v1/connectors")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "example"
    assert response.json()[0]["status"] == "healthy"
    connector_registry.clear()
