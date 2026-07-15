from fastapi import APIRouter
from app.models.schemas import Briefing
from app.services.briefing_service import BriefingService
router=APIRouter(prefix="/briefing",tags=["briefing"]); service=BriefingService()
@router.get("/today",response_model=Briefing)
def today_briefing()->Briefing:return service.build_today()
