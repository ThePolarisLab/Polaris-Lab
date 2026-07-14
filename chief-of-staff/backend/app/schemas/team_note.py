from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class TeamNoteType(str, Enum):
    INFORMATION = "INFORMATION"
    ACTION = "ACTION"
    DECISION = "DECISION"
    BLOCKER = "BLOCKER"


class TeamNoteStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class TeamNoteCreate(BaseModel):
    author: str = Field(min_length=1, max_length=120)
    note_type: TeamNoteType = TeamNoteType.INFORMATION
    title: str = Field(min_length=1, max_length=200)
    details: str = Field(min_length=1)
    target_entity: str | None = Field(default=None, max_length=255)
    assigned_to: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None


class TeamNoteUpdate(BaseModel):
    note_type: TeamNoteType | None = None
    status: TeamNoteStatus | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    details: str | None = Field(default=None, min_length=1)
    target_entity: str | None = Field(default=None, max_length=255)
    assigned_to: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None


class TeamNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author: str
    note_type: TeamNoteType
    status: TeamNoteStatus
    title: str
    details: str
    target_entity: str | None
    assigned_to: str | None
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
