from fastapi import APIRouter,Query,status
from app.models.schemas import DecisionCreate,DecisionRead
from app.repositories.decision_repository import DecisionRepository
router=APIRouter(prefix="/decisions",tags=["decisions"]); repository=DecisionRepository()
@router.post("",response_model=DecisionRead,status_code=status.HTTP_201_CREATED)
def create_decision(payload:DecisionCreate)->DecisionRead:return repository.create(payload)
@router.get("",response_model=list[DecisionRead])
def list_decisions(limit:int=Query(default=100,ge=1,le=500))->list[DecisionRead]:return repository.list(limit)
