from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.reasoning.service import analyze_q2_compliance_risk
from app.schemas.reasoning import EvidenceItemResponse, ReasoningAnalysisResponse

router = APIRouter(prefix="/reasoning", tags=["Polaris Reasoning"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/q2-risk", response_model=ReasoningAnalysisResponse)
def read_q2_risk(db: Session = Depends(get_db)):
    analysis = analyze_q2_compliance_risk(db)
    return ReasoningAnalysisResponse(
        mission_id=analysis.mission_id,
        mission_name=analysis.mission_name,
        risk=analysis.risk.value,
        confidence=analysis.confidence,
        evidence_count=analysis.evidence_count,
        recommendation=analysis.recommendation,
        evidence=[EvidenceItemResponse(
            memory_id=i.memory_id, title=i.title, details=i.details,
            category=i.category, importance=i.importance, reason=i.reason
        ) for i in analysis.evidence],
    )
