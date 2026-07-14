from fastapi import APIRouter

from app.api.routes import briefing, decisions, memories, timeline

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(memories.router)
api_router.include_router(decisions.router)
api_router.include_router(timeline.router)
api_router.include_router(briefing.router)
