from sqlalchemy.orm import Session
from app.missions.service import create_mission

def start_q2_compliance_mission(db: Session, *, owner: str = "Surinder Pahil", company: str = "MOR Logistics Manitoba Limited", due_at=None):
    return create_mission(db, template_key="q2_compliance", owner=owner, company=company, due_at=due_at)
