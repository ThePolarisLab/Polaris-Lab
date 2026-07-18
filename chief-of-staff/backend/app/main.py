from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.database import Base, engine

# Models
from app.models.company import Company
from app.models.truck import Truck
from app.models.memory import MemoryEntry
from app.models.relationship import KnowledgeRelationship
from app.missions.models import Mission, MissionTask, Workflow

# API Routers
from app.api.chat import router as chat_router
from app.api.company import router as company_router
from app.api.truck import router as truck_router
from app.api.memory import router as memory_router
from app.api.missions import router as missions_router
from app.api.relationships import router as relationships_router
from app.api.memory_search import router as memory_search_router
from app.api.reasoning import router as reasoning_router
from app.models.team_note import TeamNote
from app.api.team_notes import router as team_notes_router
from app.api.dashboard import router as dashboard_router
from app.api.github_engine import router as github_engine_router
from app.api.code_understanding import router as code_understanding_router
from app.api.work_context import router as work_context_router

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Polaris Chief of Staff API",
    version="0.4"
)

# Allow React frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(company_router)
app.include_router(truck_router)
app.include_router(memory_router)
app.include_router(chat_router)
app.include_router(missions_router)
app.include_router(relationships_router)
app.include_router(memory_search_router)
app.include_router(reasoning_router)
app.include_router(team_notes_router)
app.include_router(dashboard_router)
app.include_router(github_engine_router)
app.include_router(code_understanding_router)
app.include_router(work_context_router)


@app.get("/")
def root():
    return {
        "service": "Polaris Chief of Staff API",
        "version": "0.4",
        "database": "Connected",
        "capabilities": [
            "EXP-014B Work Context Engine",
            "PGE-002 Repository Intelligence",
            "PGE-003 Code Understanding Engine",
        ],
    }
