from pydantic import BaseModel


class EvidenceItemResponse(BaseModel):
    memory_id: int
    title: str
    details: str
    category: str
    importance: str
    reason: str


class ReasoningAnalysisResponse(BaseModel):
    mission_id: str
    mission_name: str
    risk: str
    confidence: int
    evidence_count: int
    recommendation: str
    evidence: list[EvidenceItemResponse]
