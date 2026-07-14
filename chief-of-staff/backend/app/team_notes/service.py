from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.team_note import TeamNote
from app.schemas.team_note import TeamNoteCreate, TeamNoteStatus, TeamNoteUpdate


def create_team_note(db: Session, payload: TeamNoteCreate) -> TeamNote:
    note = TeamNote(
        author=payload.author.strip(),
        note_type=payload.note_type.value,
        status=TeamNoteStatus.OPEN.value,
        title=payload.title.strip(),
        details=payload.details.strip(),
        target_entity=_clean(payload.target_entity),
        assigned_to=_clean(payload.assigned_to),
        due_at=payload.due_at,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def list_team_notes(
    db: Session,
    *,
    status: str | None = None,
    note_type: str | None = None,
    target_entity: str | None = None,
    assigned_to: str | None = None,
    limit: int = 100,
) -> list[TeamNote]:
    query = db.query(TeamNote)

    if status:
        query = query.filter(TeamNote.status == status)
    if note_type:
        query = query.filter(TeamNote.note_type == note_type)
    if target_entity:
        query = query.filter(TeamNote.target_entity == target_entity)
    if assigned_to:
        query = query.filter(TeamNote.assigned_to == assigned_to)

    return (
        query.order_by(
            TeamNote.status.asc(),
            TeamNote.due_at.asc(),
            TeamNote.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


def get_team_note(db: Session, note_id: int) -> TeamNote | None:
    return db.query(TeamNote).filter(TeamNote.id == note_id).first()


def update_team_note(db: Session, note: TeamNote, payload: TeamNoteUpdate) -> TeamNote:
    changes = payload.model_dump(exclude_unset=True)

    if "note_type" in changes:
        note.note_type = changes["note_type"].value
    if "status" in changes:
        note.status = changes["status"].value
        note.resolved_at = (
            datetime.now(timezone.utc)
            if note.status == TeamNoteStatus.RESOLVED.value
            else None
        )
    if "title" in changes:
        note.title = changes["title"].strip()
    if "details" in changes:
        note.details = changes["details"].strip()
    if "target_entity" in changes:
        note.target_entity = _clean(changes["target_entity"])
    if "assigned_to" in changes:
        note.assigned_to = _clean(changes["assigned_to"])
    if "due_at" in changes:
        note.due_at = changes["due_at"]

    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


def resolve_team_note(db: Session, note: TeamNote) -> TeamNote:
    note.status = TeamNoteStatus.RESOLVED.value
    note.resolved_at = datetime.now(timezone.utc)
    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
