from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Confidence = float
Severity = Literal["low", "medium", "high", "critical"]
ConnectorStatus = Literal["success", "partial", "failed", "skipped"]


class EntityReference(BaseModel):
    entity_type: str
    entity_id: str
    display_name: str
    confidence: Confidence = Field(ge=0, le=1)
    resolution_method: str


class Evidence(BaseModel):
    evidence_id: str
    source: str
    category: str
    summary: str
    value: Any | None = None
    observed_at: datetime | None = None
    retrieved_at: datetime
    confidence: Confidence = Field(ge=0, le=1)
    entity_refs: list[EntityReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissingInformation(BaseModel):
    field: str
    reason: str
    required_for: str
    suggested_source: str | None = None
    severity: Severity = "medium"


class Recommendation(BaseModel):
    title: str
    objective: str
    priority: Severity
    confidence: Confidence = Field(ge=0, le=1)
    reasoning_summary: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    estimated_effort_minutes: int | None = Field(default=None, ge=0)
    suggested_owner: str | None = None
    suggested_due_at: datetime | None = None


class ConnectorResult(BaseModel):
    connector: str
    status: ConnectorStatus
    evidence_count: int = Field(default=0, ge=0)
    warning: str | None = None


class WorkContextResponse(BaseModel):
    work_item_id: str
    generated_at: datetime
    entity_refs: list[EntityReference]
    evidence: list[Evidence]
    missing_information: list[MissingInformation]
    completeness_score: int = Field(ge=0, le=100)
    recommendation: Recommendation | None = None
    connector_results: list[ConnectorResult]
    warnings: list[str] = Field(default_factory=list)
