from pydantic import BaseModel

class DashboardItemResponse(BaseModel):
    title: str
    detail: str
    severity: str
    source: str
    entity_id: str | None = None

class DashboardPriorityResponse(BaseModel):
    rank: int
    title: str
    reason: str
    source: str

class ExecutiveDashboardResponse(BaseModel):
    greeting: str
    business_status: str
    review_minutes: int
    needs_attention: list[DashboardItemResponse]
    carry_forward: list[DashboardItemResponse]
    todays_plan: list[DashboardPriorityResponse]
    coming_up: list[DashboardItemResponse]
    watch_items: list[DashboardItemResponse]
    open_team_notes: int
    active_missions: int
    total_trucks: int
    recommendation: str
