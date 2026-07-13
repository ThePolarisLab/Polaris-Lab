from sqlalchemy.orm import Session
from app.reasoning.evidence import collect_mission_evidence
from app.reasoning.models import ReasoningAnalysis, RiskLevel
from app.reasoning.risk import calculate_confidence, calculate_risk

Q2_MISSION_ID = "mission.q2_compliance"
Q2_MISSION_NAME = "Complete Q2 Compliance"


def analyze_q2_compliance_risk(db: Session) -> ReasoningAnalysis:
    evidence = collect_mission_evidence(db, mission_entity_id=Q2_MISSION_ID)
    risk = calculate_risk(evidence)
    confidence = calculate_confidence(evidence)
    recommendation = _build_recommendation(risk=risk, evidence=evidence)
    return ReasoningAnalysis(
        mission_id=Q2_MISSION_ID,
        mission_name=Q2_MISSION_NAME,
        risk=risk,
        confidence=confidence,
        evidence_count=len(evidence),
        recommendation=recommendation,
        evidence=evidence,
    )


def _build_recommendation(*, risk: RiskLevel, evidence) -> str:
    if not evidence:
        return "No connected risk evidence was found. Verify that Q2 memories and relationships have been recorded."
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    highest = max(evidence, key=lambda item: order.get(item.importance.casefold(), 2))
    if risk == RiskLevel.HIGH:
        return f"Resolve the highest-priority connected issue first: {highest.details}"
    if risk == RiskLevel.MEDIUM:
        return f"Review and resolve the connected Q2 issues before filing: {highest.details}"
    return f"Continue monitoring Q2 readiness and close the remaining issue: {highest.details}"
