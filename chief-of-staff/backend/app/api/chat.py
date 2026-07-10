from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain.engine import process_message


router = APIRouter(prefix="/chat", tags=["Conversation"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    intent: str
    message: str
    reply: str


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest):
    return process_message(payload.message)