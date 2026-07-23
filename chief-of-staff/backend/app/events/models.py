"""Canonical event contracts for Polaris' internal event-driven core."""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


_EVENT_TYPE_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}\.v[1-9][0-9]*$"
)


class EventSeverity(str, Enum):
    """Operational importance assigned to an event."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DataClassification(str, Enum):
    """Minimum platform-wide information classification for an event."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class EventSource(BaseModel):
    """System component that authoritatively produced the event."""

    service: str = Field(min_length=1)
    connector: str | None = None
    instance: str | None = None


class EventActor(BaseModel):
    """Human or system actor responsible for the triggering action."""

    actor_type: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    display_name: str | None = None


class EventSubject(BaseModel):
    """Primary business object described by the event."""

    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)


class ConnectorEvent(BaseModel):
    """Immutable, tenant-aware canonical envelope for platform events.

    ``connector`` remains available as a compatibility alias while existing
    connectors migrate to the structured ``source`` contract.
    """

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(min_length=1)
    event_version: int = Field(default=1, ge=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    organization_id: str | None = None
    tenant_id: str | None = None
    workspace_id: str | None = None

    source: EventSource | None = None
    connector: str | None = None
    actor: EventActor | None = None
    subject: EventSubject | None = None
    entity: str | None = None

    severity: EventSeverity = EventSeverity.INFO
    classification: DataClassification = DataClassification.INTERNAL

    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str | None = None
    idempotency_key: str | None = None

    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        """Require the canonical ``domain.entity.action.vN`` event name."""

        if not _EVENT_TYPE_PATTERN.fullmatch(value):
            raise ValueError(
                "event_type must use lowercase domain.entity.action.vN naming"
            )
        return value

    @field_validator("occurred_at", "recorded_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Reject ambiguous timestamps and normalize valid values to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @property
    def source_name(self) -> str:
        """Return a stable source name during the connector migration."""

        if self.source is not None:
            return self.source.connector or self.source.service
        return self.connector or "unknown"


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
