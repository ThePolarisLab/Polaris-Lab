from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.dashboard.service import build_executive_dashboard
from app.database.database import SessionLocal
from app.schemas.dashboard import ExecutiveDashboardResponse

router=APIRouter(prefix="/dashboard", tags=["Executive Dashboard"])

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

@router.get("/executive", response_model=ExecutiveDashboardResponse)
def read_executive_dashboard(user_name: str = Query(default="Surinder", min_length=1, max_length=80), db: Session = Depends(get_db)):
    d=build_executive_dashboard(db,user_name=user_name)
    return {
      "greeting":d.greeting,"business_status":d.business_status,"review_minutes":d.review_minutes,
      "needs_attention":[x.__dict__ for x in d.needs_attention],"carry_forward":[x.__dict__ for x in d.carry_forward],
      "todays_plan":[x.__dict__ for x in d.todays_plan],"coming_up":[x.__dict__ for x in d.coming_up],
      "watch_items":[x.__dict__ for x in d.watch_items],"open_team_notes":d.open_team_notes,
      "active_missions":d.active_missions,"total_trucks":d.total_trucks,"recommendation":d.recommendation
    }
