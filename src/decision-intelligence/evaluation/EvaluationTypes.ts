import { DecisionEvidence, DecisionOption } from "../core";

export type EvidenceDirection = "supports" | "opposes" | "neutral";

export interface EvidenceAssessment {
  evidenceId: string;
  optionId: string;
  direction: EvidenceDirection;
  relevance: number;
  confidence: number;
  quality: number;
  weightedContribution: number;
  explanation: string;
}

export interface OptionScoreBreakdown {
  evidence: number;
  benefits: number;
  drawbacks: number;
  risks: number;
  constraints: number;
}

export interface OptionScore {
  optionId: string;
  optionTitle: string;
  total: number;
  rank: number;
  breakdown: OptionScoreBreakdown;
  evidenceAssessments: EvidenceAssessment[];
  warnings: string[];
  explanation: string[];
}

export interface DecisionEvaluationResult {
  decisionId: string;
  evaluatedAt: Date;
  scores: OptionScore[];
  tiedOptionIds: string[];
  warnings: string[];
}

export interface EvidenceEvaluationInput {
  evidence: DecisionEvidence;
  option: DecisionOption;
  direction?: EvidenceDirection;
  relevance?: number;
  quality?: number;
}

export interface ScoringWeights {
  evidence: number;
  benefits: number;
  drawbacks: number;
  risks: number;
  constraints: number;
}
