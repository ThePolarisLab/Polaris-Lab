import re
from sqlalchemy.orm import Session
from app.knowledge.relationships import relationships_for_entity
from app.models.memory import MemoryEntry
from app.reasoning.models import EvidenceItem


def collect_mission_evidence(db: Session, *, mission_entity_id: str, limit: int = 100) -> tuple[EvidenceItem, ...]:
    relationships = relationships_for_entity(db, mission_entity_id, limit=1000)
    memory_ids: set[int] = set()
    for relationship in relationships:
        for key in (relationship.source, relationship.target):
            memory_id = _memory_id_from_key(key)
            if memory_id is not None:
                memory_ids.add(memory_id)
    if not memory_ids:
        return ()
    memories = (db.query(MemoryEntry).filter(MemoryEntry.id.in_(memory_ids)).order_by(MemoryEntry.created_at.desc()).limit(limit).all())
    return tuple(EvidenceItem(
        memory_id=m.id,
        title=m.title,
        details=m.details,
        category=m.category,
        importance=m.importance,
        reason=f"Memory {m.id} is linked to {mission_entity_id} through the Knowledge Graph.",
    ) for m in memories)


def _memory_id_from_key(value: str) -> int | None:
    match = re.fullmatch(r"memory\.(\d+)", value.strip())
    return int(match.group(1)) if match else None
