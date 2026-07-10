from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.database import Base, engine
from app.models.company import Company
from app.api.company import router as company_router
from app.models.truck import Truck
from app.api.truck import router as truck_router
from app.models.memory import MemoryEntry
from app.api.memory import router as memory_router

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Polaris Chief of Staff API",
    version="0.2"
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
@app.get("/")
def root():
    return {
        "service": "Polaris Chief of Staff API",
        "version": "0.2",
        "database": "Connected"
    }