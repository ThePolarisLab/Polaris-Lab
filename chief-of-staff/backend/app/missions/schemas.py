from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class MissionTaskResponse(BaseModel):
    id: int
    title: str
    status: str
    position: int
    system: str | None
    capability: str | None
    notes: str
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)

class WorkflowResponse(BaseModel):
    id: int
    title: str
    status: str
    progress: int
    position: int
    tasks: list[MissionTaskResponse]
    model_config = ConfigDict(from_attributes=True)

class MissionResponse(BaseModel):
    id: int
    code: str
    title: str
    description: str
    status: str
    priority: str
    owner: str
    company: str
    progress: int
    created_at: datetime
    started_at: datetime | None
    due_at: datetime | None
    completed_at: datetime | None
    workflows: list[WorkflowResponse]
    model_config = ConfigDict(from_attributes=True)

class MissionCreateRequest(BaseModel):
    template_key: str = Field(min_length=1)
    owner: str = "Surinder Pahil"
    company: str = "MOR Logistics Manitoba Limited"
    due_at: datetime | None = None

class TaskStatusUpdate(BaseModel):
    status: str = Field(pattern="^(Not Started|In Progress|Blocked|Complete)$")
    notes: str | None = None
