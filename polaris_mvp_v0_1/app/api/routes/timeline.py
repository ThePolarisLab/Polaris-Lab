from fastapi import APIRouter, Query

from app.models.schemas import TimelineItem
from app.repositories.decision_repository import DecisionRepository
from app.repositories.memory_repository import MemoryRepository

router = APIRouter(prefix="/timeline", tags=["timeline"])
memories = MemoryRepository()
decisions = DecisionRepository()


@router.get("", response_model=list[TimelineItem])
def timeline(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TimelineItem]:
    items = [
        TimelineItem(
            item_type="memory",
            id=item.id,
            title=item.title,
            summary=item.content[:240],
            timestamp=item.occurred_at,
            importance=item.importance,
        )
        for item in memories.list(limit=limit)
    ]
    items.extend(
        TimelineItem(
            item_type="decision",
            id=item.id,
            title=item.title,
            summary=item.decision[:240],
            timestamp=item.decided_at,
            status=item.status.value,
        )
        for item in decisions.list(limit=limit)
    )
    return sorted(items, key=lambda item: item.timestamp, reverse=True)[:limit]
