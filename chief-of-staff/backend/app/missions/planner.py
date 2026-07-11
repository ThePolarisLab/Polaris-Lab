from datetime import datetime, timezone
from uuid import uuid4
from app.missions.models import Mission, MissionTask, Workflow

def build_mission_from_template(template: dict, *, owner: str, company: str, due_at=None) -> Mission:
    mission = Mission(
        code=f"M-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}",
        title=template["title"],
        description=template.get("description", ""),
        status="In Progress",
        priority=template.get("priority", "Medium"),
        owner=owner,
        company=company,
        progress=0,
        started_at=datetime.now(timezone.utc),
        due_at=due_at,
    )
    for wi, wt in enumerate(template.get("workflows", []), start=1):
        workflow = Workflow(title=wt["title"], status="Not Started", progress=0, position=wi)
        for ti, tt in enumerate(wt.get("tasks", []), start=1):
            workflow.tasks.append(MissionTask(
                title=tt["title"], status="Not Started", position=ti,
                system=tt.get("system"), capability=tt.get("capability")
            ))
        mission.workflows.append(workflow)
    return mission
