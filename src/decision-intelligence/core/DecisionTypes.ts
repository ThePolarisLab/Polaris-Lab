export const DECISION_STATUSES = [
  "draft",
  "evaluating",
  "recommended",
  "approved",
  "rejected",
  "implemented",
  "superseded",
] as const;

export type DecisionStatus = (typeof DECISION_STATUSES)[number];

export const EVIDENCE_TYPES = [
  "fact",
  "metric",
  "document",
  "memory",
  "graph_path",
  "expert_judgment",
] as const;

export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

export const CONSTRAINT_TYPES = [
  "budget",
  "time",
  "capacity",
  "legal",
  "policy",
  "technical",
  "strategic",
] as const;

export type ConstraintType = (typeof CONSTRAINT_TYPES)[number];

export const RISK_LEVELS = ["low", "medium", "high", "critical"] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

export type DecisionMetadata = Record<string, unknown>;
