from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.work_context.schemas import WorkContextResponse
from app.work_context.service import WorkContextService


router = APIRouter(prefix="/work-context", tags=["Work Context Engine"])
service = WorkContextService()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{work_item_id}", response_model=WorkContextResponse)
def read_work_context(
    work_item_id: str,
    entity_type: str = Query(..., min_length=1, max_length=80),
    entity_id: str = Query(..., min_length=1, max_length=120),
    display_name: str = Query(..., min_length=1, max_length=200),
    db: Session = Depends(get_db),
):
    return service.build(
        db,
        work_item_id=work_item_id,
        entity_type=entity_type,
        entity_id=entity_id,
        display_name=display_name,
    )
