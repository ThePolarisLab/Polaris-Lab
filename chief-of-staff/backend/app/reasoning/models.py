from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    memory_id: int
    title: str
    details: str
    category: str
    importance: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReasoningAnalysis:
    mission_id: str
    mission_name: str
    risk: RiskLevel
    confidence: int
    evidence_count: int
    recommendation: str
    evidence: tuple[EvidenceItem, ...]
