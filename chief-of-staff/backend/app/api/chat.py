from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.brain.engine import process_message
from app.database.database import SessionLocal

router = APIRouter(prefix="/chat", tags=["Conversation"])

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)

class ChatResponse(BaseModel):
    intent: str
    message: str
    reply: str
    action: str | None = None
    entity_id: int | None = None
    items: list[int] | None = None

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    return process_message(payload.message, db)
