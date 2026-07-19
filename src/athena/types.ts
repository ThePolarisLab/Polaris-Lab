export type AthenaIntent =
  | "general"
  | "search"
  | "knowledge"
  | "decision"
  | "analysis"
  | "business"
  | "finance"
  | "project"
  | "document"
  | "task"
  | "email"
  | "calendar"
  | "meeting"
  | "research"
  | "planning"
  | "strategy"
  | "unknown";

export type Confidence = number;

export interface AthenaRequest {
  id: string;
  userId: string;
  prompt: string;
  timestamp: Date;
  metadata?: {
    project?: string;
    organization?: string;
    priority?: "low" | "normal" | "high" | "critical";
    [key: string]: unknown;
  };
}

export interface ReasoningStep {
  id: string;
  name: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  startedAt?: Date;
  completedAt?: Date;
  detail?: string;
}

export interface ExecutionPlan {
  objective: string;
  intent: AthenaIntent;
  steps: ReasoningStep[];
}

export interface EvidenceItem {
  source: string;
  summary: string;
  relevance: number;
}

export interface AthenaContext {
  workContext: Record<string, unknown>;
  memory: Record<string, unknown>;
  knowledge: Record<string, unknown>;
}

export interface AthenaDecision {
  objective: string;
  reasoning: string[];
  evidence: EvidenceItem[];
  assumptions: string[];
  missingInformation: string[];
  confidence: Confidence;
  nextActions: string[];
}

export interface AthenaTelemetry {
  requestId: string;
  intent: AthenaIntent;
  executionTimeMs: number;
  stepCount: number;
  completedSteps: number;
  status: "completed" | "failed";
  error?: string;
}

export interface AthenaResponse {
  requestId: string;
  answer: string;
  intent: AthenaIntent;
  plan: ExecutionPlan;
  decision: AthenaDecision;
  telemetry: AthenaTelemetry;
}
