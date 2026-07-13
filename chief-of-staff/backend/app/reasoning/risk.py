from app.reasoning.models import EvidenceItem, RiskLevel


def calculate_risk(evidence: tuple[EvidenceItem, ...]) -> RiskLevel:
    count = len(evidence)
    risk = RiskLevel.HIGH if count >= 3 else RiskLevel.MEDIUM if count == 2 else RiskLevel.LOW
    has_critical = any(item.importance.casefold() == "critical" for item in evidence)
    if has_critical and risk == RiskLevel.LOW:
        return RiskLevel.MEDIUM
    if has_critical and risk == RiskLevel.MEDIUM:
        return RiskLevel.HIGH
    return risk


def calculate_confidence(evidence: tuple[EvidenceItem, ...]) -> int:
    if not evidence:
        return 35
    categories = {item.category.casefold() for item in evidence if item.category}
    score = 55 + min(len(evidence) * 10, 30) + min(len(categories) * 5, 10)
    if any(item.importance.casefold() in {"high", "critical"} for item in evidence):
        score += 5
    return min(score, 95)
