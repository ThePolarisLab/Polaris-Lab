from fastapi import APIRouter,HTTPException,Query,status
from app.models.schemas import KnowledgeCreate,KnowledgeRead,KnowledgeType,RelationshipCreate,RelationshipRead
from app.repositories.knowledge_repository import KnowledgeRepository
router=APIRouter(prefix="/knowledge",tags=["knowledge"]); repository=KnowledgeRepository()
@router.post("",response_model=KnowledgeRead,status_code=status.HTTP_201_CREATED)
def create_knowledge(payload:KnowledgeCreate)->KnowledgeRead:
    try:return repository.create(payload)
    except Exception as exc:
        if "UNIQUE constraint failed: knowledge.source_memory_id" in str(exc): raise HTTPException(409,"This memory has already been migrated to knowledge") from exc
        raise
@router.get("",response_model=list[KnowledgeRead])
def list_knowledge(query:str|None=Query(default=None,min_length=1),knowledge_type:KnowledgeType|None=None,limit:int=Query(default=100,ge=1,le=500))->list[KnowledgeRead]:
    return repository.list(query=query,knowledge_type=knowledge_type.value if knowledge_type else None,limit=limit)
@router.get("/{knowledge_id}",response_model=KnowledgeRead)
def get_knowledge(knowledge_id:int)->KnowledgeRead:
    try:return repository.get(knowledge_id)
    except KeyError as exc:raise HTTPException(404,"Knowledge object not found") from exc
@router.post("/relationships",response_model=RelationshipRead,status_code=status.HTTP_201_CREATED)
def create_relationship(payload:RelationshipCreate)->RelationshipRead:
    try:return repository.create_relationship(payload)
    except KeyError as exc:raise HTTPException(404,"Source or target knowledge object not found") from exc
@router.get("/{knowledge_id}/relationships",response_model=list[RelationshipRead])
def get_relationships(knowledge_id:int)->list[RelationshipRead]:
    try:return repository.relationships_for(knowledge_id)
    except KeyError as exc:raise HTTPException(404,"Knowledge object not found") from exc
