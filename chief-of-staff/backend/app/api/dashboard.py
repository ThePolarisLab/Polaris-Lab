from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dashboard.service import build_executive_dashboard
from app.database.database import SessionLocal
from app.schemas.dashboard import (
    DashboardItemResponse,
    DashboardPriorityResponse,
    ExecutiveDashboardResponse,
)


router = APIRouter(
    prefix="/dashboard",
    tags=["Executive Dashboard"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def serialize_item(item) -> DashboardItemResponse:
    return DashboardItemResponse(
        title=item.title,
        detail=item.detail,
        severity=item.severity,
        source=item.source,
        entity_id=item.entity_id,
    )


def serialize_priority(item) -> DashboardPriorityResponse:
    return DashboardPriorityResponse(
        rank=item.rank,
        title=item.title,
        reason=item.reason,
        source=item.source,
    )


@router.get(
    "/executive",
    response_model=ExecutiveDashboardResponse,
)
def read_executive_dashboard(
    user_name: str = Query(
        default="Surinder",
        min_length=1,
        max_length=80,
    ),
    db: Session = Depends(get_db),
):
    dashboard = build_executive_dashboard(
        db,
        user_name=user_name,
    )

    return ExecutiveDashboardResponse(
        greeting=dashboard.greeting,
        business_status=dashboard.business_status,
        review_minutes=dashboard.review_minutes,
        needs_attention=[
            serialize_item(item)
            for item in dashboard.needs_attention
        ],
        carry_forward=[
            serialize_item(item)
            for item in dashboard.carry_forward
        ],
        todays_plan=[
            serialize_priority(item)
            for item in dashboard.todays_plan
        ],
        coming_up=[
            serialize_item(item)
            for item in dashboard.coming_up
        ],
        watch_items=[
            serialize_item(item)
            for item in dashboard.watch_items
        ],
        open_team_notes=dashboard.open_team_notes,
        active_missions=dashboard.active_missions,
        total_trucks=dashboard.total_trucks,
        recommendation=dashboard.recommendation,
    )