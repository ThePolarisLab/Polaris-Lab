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
class DailyBrief:
    todays_priority: tuple[DashboardPriority, ...]
    needs_attention: tuple[DashboardItem, ...]
    ace_summary: tuple[DashboardItem, ...]
    carry_forward: tuple[DashboardItem, ...]
    waiting_on: tuple[DashboardItem, ...]
    system_health: tuple[DashboardItem, ...]


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
    daily_brief: DailyBrief
