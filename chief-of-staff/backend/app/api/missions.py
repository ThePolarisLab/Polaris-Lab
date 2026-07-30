from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.missions.schemas import MissionCreateRequest, MissionResponse, MissionTaskResponse, TaskStatusUpdate
from app.missions.service import create_mission, get_mission, list_missions, update_task_status
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission

router = APIRouter(prefix="/missions", tags=["Missions"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=list[MissionResponse])
def read_missions(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    return list_missions(db, principal.organization_id)

@router.get("/{mission_id}", response_model=MissionResponse)
def read_mission(
    mission_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    return get_mission(db, principal.organization_id, mission_id)

@router.post("", response_model=MissionResponse, status_code=status.HTTP_201_CREATED)
def create_registered_mission(
    payload: MissionCreateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_WRITE)),
    db: Session = Depends(get_db),
):
    return create_mission(db, organization_id=principal.organization_id, template_key=payload.template_key, owner=payload.owner, company=payload.company, due_at=payload.due_at)

@router.patch("/tasks/{task_id}", response_model=MissionTaskResponse)
def change_task_status(
    task_id: int,
    payload: TaskStatusUpdate,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_WRITE)),
    db: Session = Depends(get_db),
):
    return update_task_status(db, organization_id=principal.organization_id, task_id=task_id, status=payload.status, notes=payload.notes)
