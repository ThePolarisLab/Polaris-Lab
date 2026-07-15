from fastapi import APIRouter,Query
from app.models.schemas import TimelineItem
from app.repositories.memory_repository import MemoryRepository
from app.repositories.decision_repository import DecisionRepository
router=APIRouter(prefix="/timeline",tags=["timeline"]); memories=MemoryRepository(); decisions=DecisionRepository()
@router.get("",response_model=list[TimelineItem])
def timeline(limit:int=Query(default=100,ge=1,le=500))->list[TimelineItem]:
    items=[TimelineItem(item_type="memory",id=m.id,title=m.title,summary=m.content[:240],timestamp=m.occurred_at,importance=m.importance) for m in memories.list(limit=limit)]
    items += [TimelineItem(item_type="decision",id=d.id,title=d.title,summary=d.decision[:240],timestamp=d.decided_at,status=d.status.value) for d in decisions.list(limit=limit)]
    return sorted(items,key=lambda i:i.timestamp,reverse=True)[:limit]
