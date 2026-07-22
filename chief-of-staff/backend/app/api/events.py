"""Builder-facing operational endpoints for the Polaris event bus."""

from fastapi import APIRouter, Query

from app.events import ConnectorEvent, EventBusHealth, EventBusMetrics, event_bus

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/health", response_model=EventBusHealth)
def event_health() -> EventBusHealth:
    metrics = event_bus.metrics()
    status = "healthy" if metrics.deliveries_failed == 0 else "degraded"
    return EventBusHealth(status=status, metrics=metrics)


@router.get("/metrics", response_model=EventBusMetrics)
def event_metrics() -> EventBusMetrics:
    return event_bus.metrics()


@router.get("/recent", response_model=list[ConnectorEvent])
def recent_events(limit: int = Query(default=20, ge=1, le=100)) -> list[ConnectorEvent]:
    return event_bus.recent(limit)
