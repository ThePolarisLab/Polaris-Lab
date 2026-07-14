from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    NOTE = "note"
    MEETING = "meeting"
    DECISION = "decision"
    LESSON = "lesson"
    PROJECT = "project"
    CUSTOMER = "customer"
    OPERATIONAL = "operational"


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REVERSED = "reversed"


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    memory_type: MemoryType = MemoryType.NOTE
    source: str = Field(default="builder", min_length=1, max_length=100)
    importance: int = Field(default=3, ge=1, le=5)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryRead(MemoryCreate):
    id: int
    created_at: datetime


class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    status: DecisionStatus = DecisionStatus.APPROVED
    decided_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionRead(DecisionCreate):
    id: int
    created_at: datetime


class TimelineItem(BaseModel):
    item_type: str
    id: int
    title: str
    summary: str
    timestamp: datetime
    importance: int | None = None
    status: str | None = None


class Briefing(BaseModel):
    date: str
    headline: str
    priorities: list[TimelineItem]
    recent_decisions: list[DecisionRead]
    memory_count: int
    decision_count: int
