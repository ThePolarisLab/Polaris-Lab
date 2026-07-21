import { EvidenceAssessment } from "../evaluation";
import { DecisionRecommendationResult, OptionTradeOff } from "../recommendation";

export interface EvidenceTrace {
  evidenceId: string;
  optionId: string;
  direction: EvidenceAssessment["direction"];
  weightedContribution: number;
  explanation: string;
}

export interface DecisionAuditRecord {
  decisionId: string;
  recommendationStatus: DecisionRecommendationResult["status"];
  selectedOptionId?: string;
  selectedOptionTitle?: string;
  confidence: number;
  generatedAt: Date;
  evaluationTimestamp: Date;
  evidenceTrace: EvidenceTrace[];
  alternatives: OptionTradeOff[];
  rationale: string[];
  warnings: string[];
  replayFingerprint: string;
  deterministic: true;
}
