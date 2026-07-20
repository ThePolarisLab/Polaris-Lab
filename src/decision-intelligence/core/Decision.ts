import {
  ConstraintType,
  DecisionMetadata,
  DecisionStatus,
  EvidenceType,
  RiskLevel,
} from "./DecisionTypes";

export interface DecisionEvidence {
  id: string;
  type: EvidenceType;
  title: string;
  sourceRef?: string;
  summary: string;
  confidence: number;
  metadata: DecisionMetadata;
}

export interface DecisionConstraint {
  id: string;
  type: ConstraintType;
  description: string;
  mandatory: boolean;
  metadata: DecisionMetadata;
}

export interface DecisionRisk {
  id: string;
  title: string;
  description: string;
  likelihood: number;
  impact: number;
  level: RiskLevel;
  mitigation?: string;
  metadata: DecisionMetadata;
}

export interface DecisionOption {
  id: string;
  title: string;
  description: string;
  benefits: string[];
  drawbacks: string[];
  evidenceIds: string[];
  constraintIds: string[];
  riskIds: string[];
  score?: number;
  metadata: DecisionMetadata;
}

export interface DecisionRecommendation {
  optionId: string;
  rationale: string;
  confidence: number;
  recommendedAt: Date;
}

export interface DecisionOutcome {
  optionId: string;
  summary: string;
  recordedAt: Date;
  metadata: DecisionMetadata;
}

export interface Decision {
  id: string;
  title: string;
  question: string;
  status: DecisionStatus;
  options: DecisionOption[];
  evidence: DecisionEvidence[];
  constraints: DecisionConstraint[];
  risks: DecisionRisk[];
  recommendation?: DecisionRecommendation;
  outcome?: DecisionOutcome;
  tags: string[];
  metadata: DecisionMetadata;
  version: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface CreateDecisionInput {
  id?: string;
  title: string;
  question: string;
  tags?: string[];
  metadata?: DecisionMetadata;
}
