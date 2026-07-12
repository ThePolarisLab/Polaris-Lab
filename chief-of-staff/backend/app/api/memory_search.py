from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.knowledge.search import search_memories
from app.schemas.memory_search import MemorySearchResultResponse


router = APIRouter(
    prefix="/memory-search",
    tags=["Knowledge Search"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.get(
    "",
    response_model=list[MemorySearchResultResponse],
)
def read_memory_search(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    results = search_memories(
        db,
        q,
        limit=limit,
    )

    return [
        MemorySearchResultResponse(
            id=result.memory.id,
            category=result.memory.category,
            title=result.memory.title,
            details=result.memory.details,
            importance=result.memory.importance,
            source=result.memory.source,
            created_at=result.memory.created_at,
            score=result.score,
            reasons=list(result.reasons),
        )
        for result in results
    ]
