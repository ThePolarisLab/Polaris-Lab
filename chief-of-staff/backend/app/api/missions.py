from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.missions.schemas import MissionCreateRequest, MissionResponse, MissionTaskResponse, TaskStatusUpdate
from app.missions.service import create_mission, get_mission, list_missions, update_task_status

router = APIRouter(prefix="/missions", tags=["Missions"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=list[MissionResponse])
def read_missions(db: Session = Depends(get_db)):
    return list_missions(db)

@router.get("/{mission_id}", response_model=MissionResponse)
def read_mission(mission_id: int, db: Session = Depends(get_db)):
    return get_mission(db, mission_id)

@router.post("", response_model=MissionResponse, status_code=status.HTTP_201_CREATED)
def create_registered_mission(payload: MissionCreateRequest, db: Session = Depends(get_db)):
    return create_mission(db, template_key=payload.template_key, owner=payload.owner, company=payload.company, due_at=payload.due_at)

@router.patch("/tasks/{task_id}", response_model=MissionTaskResponse)
def change_task_status(task_id: int, payload: TaskStatusUpdate, db: Session = Depends(get_db)):
    return update_task_status(db, task_id=task_id, status=payload.status, notes=payload.notes)
