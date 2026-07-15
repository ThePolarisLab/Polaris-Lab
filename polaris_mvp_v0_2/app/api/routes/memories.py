from fastapi import APIRouter,HTTPException,Query,status
from app.models.schemas import MemoryCreate,MemoryRead
from app.repositories.memory_repository import MemoryRepository
router=APIRouter(prefix="/memories",tags=["memories"]); repository=MemoryRepository()
@router.post("",response_model=MemoryRead,status_code=status.HTTP_201_CREATED)
def create_memory(payload:MemoryCreate)->MemoryRead:return repository.create(payload)
@router.get("",response_model=list[MemoryRead])
def list_memories(query:str|None=Query(default=None,min_length=1),limit:int=Query(default=100,ge=1,le=500))->list[MemoryRead]:return repository.list(query=query,limit=limit)
@router.get("/{memory_id}",response_model=MemoryRead)
def get_memory(memory_id:int)->MemoryRead:
    try:return repository.get(memory_id)
    except KeyError as exc:raise HTTPException(404,"Memory not found") from exc
