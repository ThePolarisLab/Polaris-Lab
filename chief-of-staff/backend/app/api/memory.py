from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.memory import MemoryEntry


router = APIRouter(prefix="/memory", tags=["Memory"])


class MemoryCreate(BaseModel):
    category: str
    title: str
    details: str
    importance: str = "Medium"
    source: str = "Manual"


class MemoryResponse(MemoryCreate):
    id: int
    created_at: object

    model_config = ConfigDict(from_attributes=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[MemoryResponse])
def get_memories(db: Session = Depends(get_db)):
    return (
        db.query(MemoryEntry)
        .order_by(MemoryEntry.created_at.desc())
        .all()
    )


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_memory(
    payload: MemoryCreate,
    db: Session = Depends(get_db),
):
    entry = MemoryEntry(**payload.model_dump())

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry