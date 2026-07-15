from app.core.database import initialize_database
from app.models.schemas import KnowledgeCreate,KnowledgeType,TruthStatus,Visibility
from app.repositories.memory_repository import MemoryRepository
from app.repositories.knowledge_repository import KnowledgeRepository

def map_type(memory_type:str)->KnowledgeType:
    return {"lesson":KnowledgeType.LESSON_LEARNED,"decision":KnowledgeType.DECISION,"meeting":KnowledgeType.MEETING,"project":KnowledgeType.PROJECT}.get(memory_type,KnowledgeType.ORGANIZATIONAL_MEMORY)

def main()->None:
    initialize_database(); memories=MemoryRepository(); knowledge=KnowledgeRepository(); created=0; skipped=0
    for memory in memories.list(limit=10000):
        try:
            knowledge.create(KnowledgeCreate(title=memory.title,content=memory.content,knowledge_type=map_type(memory.memory_type.value),author=memory.source,importance=memory.importance,confidence=1.0,truth_status=TruthStatus.ASSERTED,source=f"memory:{memory.id}",source_memory_id=memory.id,visibility=Visibility.ORGANIZATION))
            created+=1
        except Exception as exc:
            if "UNIQUE constraint failed: knowledge.source_memory_id" in str(exc): skipped+=1
            else: raise
    print(f"Migration complete. Created: {created}; already migrated: {skipped}.")
if __name__=="__main__":main()
