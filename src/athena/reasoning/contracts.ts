export type EvidenceStrength = "weak" | "moderate" | "strong";
export type InsightPriority = "informational" | "low" | "medium" | "high" | "critical";

export interface ReasoningEvidence {
  id: string;
  organizationId: string;
  domain: string;
  source: string;
  observedAt: Date;
  summary: string;
  strength: EvidenceStrength;
  reliability: number;
  completeness: number;
  attributes?: Record<string, unknown>;
}

export interface ReasoningContext {
  requestId: string;
  organizationId: string;
  objective: string;
  generatedAt: Date;
  evidence: ReasoningEvidence[];
}

export interface Finding {
  id: string;
  title: string;
  description: string;
  domain: string;
  evidenceIds: string[];
  impact: number;
  urgency: number;
  attributes?: Record<string, unknown>;
}

export interface Recommendation {
  id: string;
  findingId: string;
  action: string;
  rationale: string;
  expectedImpact: string;
}

export interface ConfidenceAssessment {
  score: number;
  level: "low" | "medium" | "high";
  reasons: string[];
  conflicts: string[];
}

export interface ExecutiveInsight {
  finding: Finding;
  priority: InsightPriority;
  confidence: ConfidenceAssessment;
  evidence: ReasoningEvidence[];
  recommendation?: Recommendation;
  explanation: string;
}

export interface AthenaReasoningResult {
  requestId: string;
  organizationId: string;
  objective: string;
  generatedAt: Date;
  summary: string;
  insights: ExecutiveInsight[];
}

export interface ReasoningRule {
  id: string;
  evaluate(context: ReasoningContext): Finding[];
}

export interface RecommendationPolicy {
  recommend(finding: Finding, evidence: ReasoningEvidence[]): Recommendation | undefined;
}
