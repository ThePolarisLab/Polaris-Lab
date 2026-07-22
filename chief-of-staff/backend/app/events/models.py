"""Normalized event contracts for Polaris' internal event-driven core."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventSeverity(str, Enum):
    """Operational importance assigned to an event."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ConnectorEvent(BaseModel):
    """Immutable envelope published by connectors and platform services."""

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    connector: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    entity: str | None = None
    severity: EventSeverity = EventSeverity.INFO
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class EventBusMetrics(BaseModel):
    """Operational metrics exposed by the in-process event bus."""

    events_published: int = 0
    deliveries_attempted: int = 0
    deliveries_succeeded: int = 0
    deliveries_failed: int = 0
    subscriber_count: int = 0
    retained_events: int = 0
    last_published_at: datetime | None = None


class EventBusHealth(BaseModel):
    """Machine-readable event bus health response."""

    status: str
    metrics: EventBusMetrics
