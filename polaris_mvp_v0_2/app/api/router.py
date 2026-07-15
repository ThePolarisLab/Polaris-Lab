from fastapi import APIRouter
from app.api.routes import memories, decisions, timeline, briefing, knowledge
api_router=APIRouter(prefix="/api/v1")
for router in (memories.router,decisions.router,timeline.router,briefing.router,knowledge.router): api_router.include_router(router)
