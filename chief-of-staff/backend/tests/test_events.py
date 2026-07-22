from fastapi.testclient import TestClient

from app.events import ConnectorEvent, EventBus
from app.main import app


def test_event_bus_delivers_in_order_and_retains_recent_events():
    bus = EventBus(history_size=2)
    received: list[str] = []
    bus.subscribe("memory", lambda event: received.append(event.event_type))

    bus.publish(ConnectorEvent(connector="github", event_type="pull_request.opened"))
    bus.publish(ConnectorEvent(connector="github", event_type="check.completed"))
    bus.publish(ConnectorEvent(connector="github", event_type="pull_request.merged"))

    assert received == [
        "pull_request.opened",
        "check.completed",
        "pull_request.merged",
    ]
    assert [event.event_type for event in bus.recent()] == [
        "pull_request.merged",
        "check.completed",
    ]


def test_event_bus_rejects_duplicate_subscribers_and_unsubscribes():
    bus = EventBus()
    bus.subscribe("Athena", lambda event: None)

    try:
        bus.subscribe("athena", lambda event: None)
        assert False, "duplicate subscriber should fail"
    except ValueError as exc:
        assert "already registered" in str(exc)

    assert bus.unsubscribe("ATHENA") is True
    assert bus.unsubscribe("athena") is False


def test_subscriber_failure_does_not_stop_other_consumers():
    bus = EventBus()
    delivered: list[str] = []

    def broken_handler(event: ConnectorEvent) -> None:
        raise RuntimeError("consumer unavailable")

    bus.subscribe("broken", broken_handler)
    bus.subscribe("healthy", lambda event: delivered.append(event.event_type))

    failures = bus.publish(ConnectorEvent(connector="github", event_type="push"))
    metrics = bus.metrics()

    assert failures == ["broken"]
    assert delivered == ["push"]
    assert metrics.events_published == 1
    assert metrics.deliveries_attempted == 2
    assert metrics.deliveries_succeeded == 1
    assert metrics.deliveries_failed == 1
    assert metrics.subscriber_count == 2
    assert metrics.retained_events == 1


def test_event_api_exposes_health_metrics_and_recent_events():
    client = TestClient(app)

    health = client.get("/api/v1/events/health")
    metrics = client.get("/api/v1/events/metrics")
    recent = client.get("/api/v1/events/recent?limit=5")

    assert health.status_code == 200
    assert health.json()["status"] in {"healthy", "degraded"}
    assert metrics.status_code == 200
    assert "events_published" in metrics.json()
    assert recent.status_code == 200
    assert isinstance(recent.json(), list)
