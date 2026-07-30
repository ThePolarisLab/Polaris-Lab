from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.memory import MemoryEntry
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal, Permission


router = APIRouter(prefix="/memory", tags=["Memory"])


class MemoryCreate(BaseModel):
    category: str
    title: str
    details: str
    importance: str = "Medium"
    source: str = "Manual"


class MemoryResponse(MemoryCreate):
    id: int
    organization_id: str
    created_at: object

    model_config = ConfigDict(from_attributes=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[MemoryResponse])
def get_memories(
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_READ)),
    db: Session = Depends(get_db),
):
    return (
        db.query(MemoryEntry)
        .filter(MemoryEntry.organization_id == principal.organization_id)
        .order_by(MemoryEntry.created_at.desc())
        .all()
    )


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    principal: AuthenticatedPrincipal = Depends(require_permission(Permission.EXECUTIVE_WRITE)),
    db: Session = Depends(get_db),
):
    entry = MemoryEntry(organization_id=principal.organization_id, **payload.model_dump())

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry