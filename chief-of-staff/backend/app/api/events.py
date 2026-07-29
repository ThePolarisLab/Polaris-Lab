"""Builder-facing operational endpoints for the Polaris event bus."""

from fastapi import APIRouter, Depends, Query

from app.events import ConnectorEvent, EventBusHealth, EventBusMetrics, event_bus
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/health", response_model=EventBusHealth)
def event_health(
    _: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_READ)),
) -> EventBusHealth:
    metrics = event_bus.metrics()
    status = "healthy" if metrics.deliveries_failed == 0 else "degraded"
    return EventBusHealth(status=status, metrics=metrics)


@router.get("/metrics", response_model=EventBusMetrics)
def event_metrics(
    _: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_READ)),
) -> EventBusMetrics:
    return event_bus.metrics()


@router.get("/recent", response_model=list[ConnectorEvent])
def recent_events(
    limit: int = Query(default=20, ge=1, le=100),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.ORGANIZATION_READ)),
) -> list[ConnectorEvent]:
    return [
        event
        for event in event_bus.recent(limit=100)
        if event.organization_id in {None, principal.organization_id}
        or event.tenant_id in {None, principal.organization_id}
    ][:limit]
