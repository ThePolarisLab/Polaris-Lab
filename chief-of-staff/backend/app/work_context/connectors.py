from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.missions.models import Mission
from app.models.memory import MemoryEntry
from app.models.team_note import TeamNote
from app.work_context.schemas import ConnectorResult, EntityReference, Evidence


class ContextConnector(Protocol):
    name: str

    def supports(self, entity_type: str) -> bool: ...

    def fetch_context(
        self,
        db: Session,
        entity: EntityReference,
    ) -> tuple[list[Evidence], ConnectorResult]: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TeamNotesConnector:
    name = "team_notes"

    def supports(self, entity_type: str) -> bool:
        return True

    def fetch_context(self, db: Session, entity: EntityReference):
        query = db.query(TeamNote).filter(TeamNote.status != "RESOLVED")
        query = query.filter(
            or_(
                TeamNote.target_entity.ilike(f"%{entity.display_name}%"),
                TeamNote.title.ilike(f"%{entity.display_name}%"),
                TeamNote.details.ilike(f"%{entity.display_name}%"),
            )
        )
        notes = query.order_by(TeamNote.updated_at.desc()).limit(10).all()
        evidence = [
            Evidence(
                evidence_id=f"team-note:{note.id}",
                source=self.name,
                category=note.note_type.lower(),
                summary=note.title,
                value={"details": note.details, "status": note.status, "assigned_to": note.assigned_to},
                observed_at=note.updated_at,
                retrieved_at=_now(),
                confidence=0.9,
                entity_refs=[entity],
            )
            for note in notes
        ]
        return evidence, ConnectorResult(connector=self.name, status="success", evidence_count=len(evidence))


class MemoryConnector:
    name = "memory"

    def supports(self, entity_type: str) -> bool:
        return True

    def fetch_context(self, db: Session, entity: EntityReference):
        memories = (
            db.query(MemoryEntry)
            .filter(
                or_(
                    MemoryEntry.title.ilike(f"%{entity.display_name}%"),
                    MemoryEntry.details.ilike(f"%{entity.display_name}%"),
                )
            )
            .order_by(MemoryEntry.created_at.desc())
            .limit(10)
            .all()
        )
        evidence = [
            Evidence(
                evidence_id=f"memory:{memory.id}",
                source=self.name,
                category=memory.category,
                summary=memory.title,
                value={"details": memory.details, "importance": memory.importance, "source": memory.source},
                observed_at=memory.created_at,
                retrieved_at=_now(),
                confidence=0.8,
                entity_refs=[entity],
            )
            for memory in memories
        ]
        return evidence, ConnectorResult(connector=self.name, status="success", evidence_count=len(evidence))


class MissionsConnector:
    name = "missions"

    def supports(self, entity_type: str) -> bool:
        return True

    def fetch_context(self, db: Session, entity: EntityReference):
        missions = (
            db.query(Mission)
            .filter(
                Mission.status != "Completed",
                or_(
                    Mission.title.ilike(f"%{entity.display_name}%"),
                    Mission.description.ilike(f"%{entity.display_name}%"),
                    Mission.company.ilike(f"%{entity.display_name}%"),
                ),
            )
            .order_by(Mission.due_at.asc(), Mission.created_at.desc())
            .limit(10)
            .all()
        )
        evidence = [
            Evidence(
                evidence_id=f"mission:{mission.id}",
                source=self.name,
                category="mission",
                summary=mission.title,
                value={"code": mission.code, "status": mission.status, "priority": mission.priority, "progress": mission.progress, "owner": mission.owner},
                observed_at=mission.started_at or mission.created_at,
                retrieved_at=_now(),
                confidence=0.9,
                entity_refs=[entity],
                metadata={"due_at": mission.due_at.isoformat() if mission.due_at else None},
            )
            for mission in missions
        ]
        return evidence, ConnectorResult(connector=self.name, status="success", evidence_count=len(evidence))
