from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.knowledge.relationships import (
    list_relationships,
    relationships_for_entity,
)
from app.schemas.relationship import RelationshipResponse


router = APIRouter(
    prefix="/relationships",
    tags=["Knowledge Relationships"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.get(
    "",
    response_model=list[RelationshipResponse],
)
def read_relationships(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return list_relationships(
        db,
        limit=limit,
    )


@router.get(
    "/entity/{entity_key}",
    response_model=list[RelationshipResponse],
)
def read_entity_relationships(
    entity_key: str,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return relationships_for_entity(
        db,
        entity_key,
        limit=limit,
    )
