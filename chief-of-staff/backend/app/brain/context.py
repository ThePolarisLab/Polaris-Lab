from sqlalchemy.orm import Session
from app.models.memory import MemoryEntry
from app.missions.models import Mission

def load_context(db: Session) -> dict:
    recent_memories = db.query(MemoryEntry).order_by(MemoryEntry.created_at.desc()).limit(5).all()
    active_missions = db.query(Mission).filter(Mission.status != "Complete").order_by(Mission.created_at.desc()).limit(5).all()
    return {"recent_memories": recent_memories, "active_missions": active_missions}
