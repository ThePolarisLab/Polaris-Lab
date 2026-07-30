from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.schemas.team_note import (
    TeamNoteCreate,
    TeamNoteResponse,
    TeamNoteStatus,
    TeamNoteType,
    TeamNoteUpdate,
)
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission
from app.team_notes.service import (
    create_team_note,
    get_team_note,
    list_team_notes,
    resolve_team_note,
    update_team_note,
)

router = APIRouter(prefix="/team-notes", tags=["Team Notes"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=TeamNoteResponse, status_code=201)
def create_note(
    payload: TeamNoteCreate,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_WRITE)),
    db: Session = Depends(get_db),
):
    return create_team_note(db, principal.organization_id, payload)


@router.get("", response_model=list[TeamNoteResponse])
def read_notes(
    status: TeamNoteStatus | None = None,
    note_type: TeamNoteType | None = None,
    target_entity: str | None = None,
    assigned_to: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    return list_team_notes(
        db,
        principal.organization_id,
        status=status.value if status else None,
        note_type=note_type.value if note_type else None,
        target_entity=target_entity,
        assigned_to=assigned_to,
        limit=limit,
    )


@router.get("/{note_id}", response_model=TeamNoteResponse)
def read_note(
    note_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    note = get_team_note(db, principal.organization_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Team note not found.")
    return note


@router.patch("/{note_id}", response_model=TeamNoteResponse)
def patch_note(
    note_id: int,
    payload: TeamNoteUpdate,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_WRITE)),
    db: Session = Depends(get_db),
):
    note = get_team_note(db, principal.organization_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Team note not found.")
    return update_team_note(db, note, payload)


@router.post("/{note_id}/resolve", response_model=TeamNoteResponse)
def resolve_note(
    note_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_WRITE)),
    db: Session = Depends(get_db),
):
    note = get_team_note(db, principal.organization_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Team note not found.")
    return resolve_team_note(db, note)
