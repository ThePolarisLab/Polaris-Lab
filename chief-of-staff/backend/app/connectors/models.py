"""Shared models for connector lifecycle and observability."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConnectorStatus(str, Enum):
    """Normalized connector states exposed throughout Polaris."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    AUTHENTICATION_ERROR = "authentication_error"
    CONFIGURATION_ERROR = "configuration_error"
    SYNC_ERROR = "sync_error"
    NOT_CONFIGURED = "not_configured"
    CONFIGURED_UNVERIFIED = "configured_unverified"
    CONNECTED = "connected"
    AUTHORIZATION_REQUIRED = "authorization_required"
    CONNECTED_UNVERIFIED = "connected_unverified"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    COMPANY_MISMATCH = "company_mismatch"
    RATE_LIMITED = "rate_limited"
    SYNCHRONIZATION_FAILED = "synchronization_failed"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"


class ConnectorHealth(BaseModel):
    """Current operational state of one connector."""

    name: str
    status: ConnectorStatus
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float | None = None
    last_sync_at: datetime | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SyncResult(BaseModel):
    """Normalized result returned by connector synchronization operations."""

    connector: str
    started_at: datetime
    completed_at: datetime
    records_read: int = 0
    records_written: int = 0
    events_published: int = 0
    success: bool = True
    errors: list[str] = Field(default_factory=list)