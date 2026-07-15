from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DashboardItem:
    title: str
    detail: str
    severity: str
    source: str
    entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardPriority:
    rank: int
    title: str
    reason: str
    source: str


@dataclass(frozen=True, slots=True)
class ExecutiveDashboard:
    greeting: str
    business_status: str
    review_minutes: int
    needs_attention: tuple[DashboardItem, ...]
    carry_forward: tuple[DashboardItem, ...]
    todays_plan: tuple[DashboardPriority, ...]
    coming_up: tuple[DashboardItem, ...]
    watch_items: tuple[DashboardItem, ...]
    open_team_notes: int
    active_missions: int
    total_trucks: int
    recommendation: str
