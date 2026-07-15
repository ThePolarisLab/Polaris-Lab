from datetime import date
from app.models.schemas import Briefing, TimelineItem
from app.repositories.memory_repository import MemoryRepository
from app.repositories.decision_repository import DecisionRepository
from app.repositories.knowledge_repository import KnowledgeRepository
class BriefingService:
    def __init__(self):
        self.memories=MemoryRepository(); self.decisions=DecisionRepository(); self.knowledge=KnowledgeRepository()
    def build_today(self)->Briefing:
        memories=self.memories.list(limit=50); decisions=self.decisions.list(limit=5); knowledge=self.knowledge.list(limit=5)
        priorities=sorted([TimelineItem(item_type="memory",id=m.id,title=m.title,summary=m.content[:240],timestamp=m.occurred_at,importance=m.importance) for m in memories if m.importance>=4],key=lambda i:(i.importance or 0,i.timestamp),reverse=True)[:5]
        return Briefing(date=date.today().isoformat(),headline="Focus on priority memories, recent decisions, and enduring knowledge.",priorities=priorities,recent_decisions=decisions,featured_knowledge=knowledge,memory_count=self.memories.count(),decision_count=self.decisions.count(),knowledge_count=self.knowledge.count())
