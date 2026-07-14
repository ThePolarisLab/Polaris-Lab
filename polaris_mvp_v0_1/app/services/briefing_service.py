from datetime import date

from app.models.schemas import Briefing, TimelineItem
from app.repositories.decision_repository import DecisionRepository
from app.repositories.memory_repository import MemoryRepository


class BriefingService:
    def __init__(
        self,
        memories: MemoryRepository | None = None,
        decisions: DecisionRepository | None = None,
    ) -> None:
        self.memories = memories or MemoryRepository()
        self.decisions = decisions or DecisionRepository()

    def build_today(self) -> Briefing:
        memories = self.memories.list(limit=50)
        decisions = self.decisions.list(limit=5)

        priorities = sorted(
            [
                TimelineItem(
                    item_type="memory",
                    id=memory.id,
                    title=memory.title,
                    summary=memory.content[:240],
                    timestamp=memory.occurred_at,
                    importance=memory.importance,
                )
                for memory in memories
                if memory.importance >= 4
            ],
            key=lambda item: (item.importance or 0, item.timestamp),
            reverse=True,
        )[:5]

        return Briefing(
            date=date.today().isoformat(),
            headline="Focus on the highest-importance memories and recent decisions.",
            priorities=priorities,
            recent_decisions=decisions,
            memory_count=self.memories.count(),
            decision_count=self.decisions.count(),
        )
