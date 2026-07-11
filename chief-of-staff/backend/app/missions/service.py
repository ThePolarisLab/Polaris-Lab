from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.missions.models import Mission, MissionTask
from app.missions.planner import build_mission_from_template
from app.missions.registry import get_template

def create_mission(db: Session, *, template_key: str, owner: str, company: str, due_at=None) -> Mission:
    template = get_template(template_key)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Mission template '{template_key}' was not found.")
    mission = build_mission_from_template(template, owner=owner, company=company, due_at=due_at)
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission

def list_missions(db: Session) -> list[Mission]:
    return db.query(Mission).order_by(Mission.created_at.desc()).all()

def get_mission(db: Session, mission_id: int) -> Mission:
    mission = db.query(Mission).filter(Mission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return mission

def update_task_status(db: Session, *, task_id: int, status: str, notes: str | None = None) -> MissionTask:
    task = db.query(MissionTask).filter(MissionTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    task.status = status
    if notes is not None:
        task.notes = notes
    task.completed_at = datetime.now(timezone.utc) if status == "Complete" else None
    _recalculate_progress(task.workflow.mission)
    db.commit()
    db.refresh(task)
    return task

def _recalculate_progress(mission: Mission) -> None:
    all_tasks = [task for workflow in mission.workflows for task in workflow.tasks]
    if not all_tasks:
        mission.progress = 0
        return
    for workflow in mission.workflows:
        total = len(workflow.tasks)
        complete = sum(task.status == "Complete" for task in workflow.tasks)
        workflow.progress = round((complete / total) * 100) if total else 0
        workflow.status = "Not Started" if complete == 0 else ("Complete" if complete == total else "In Progress")
    completed = sum(task.status == "Complete" for task in all_tasks)
    mission.progress = round((completed / len(all_tasks)) * 100)
    mission.status = "Complete" if mission.progress == 100 else "In Progress"
    mission.completed_at = datetime.now(timezone.utc) if mission.progress == 100 else None
