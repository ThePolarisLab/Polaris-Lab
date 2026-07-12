from datetime import datetime

from pydantic import BaseModel


class MemorySearchResultResponse(BaseModel):
    id: int
    category: str
    title: str
    details: str
    importance: str
    source: str
    created_at: datetime
    score: int
    reasons: list[str]
