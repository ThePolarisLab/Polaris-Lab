from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.router import api_router
from app.core.database import initialize_database

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="Polaris",
    version="0.2.0",
    description="Memory-first organizational intelligence for Builders.",
    lifespan=lifespan,
)
app.include_router(api_router)

@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name":"Polaris","version":"0.2.0","motto":"Build Better Decisions."}

@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status":"ok"}
