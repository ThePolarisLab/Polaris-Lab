import {
  AthenaContext,
  AthenaDecision,
  AthenaIntent,
  AthenaRequest,
  ExecutionPlan,
} from "./types";

export interface IntentClassifier {
  classify(request: AthenaRequest): Promise<AthenaIntent>;
}

export interface ExecutionPlanner {
  createPlan(request: AthenaRequest, intent: AthenaIntent): Promise<ExecutionPlan>;
}

export interface ContextAssembler {
  assemble(request: AthenaRequest, plan: ExecutionPlan): Promise<AthenaContext>;
}

export interface DecisionEngine {
  decide(
    request: AthenaRequest,
    plan: ExecutionPlan,
    context: AthenaContext,
  ): Promise<AthenaDecision>;
}

export interface ResponseBuilder {
  buildAnswer(
    request: AthenaRequest,
    decision: AthenaDecision,
    context: AthenaContext,
  ): Promise<string>;
}

export interface MemoryService {
  remember(request: AthenaRequest, decision: AthenaDecision): Promise<void>;
}

export interface TelemetrySink {
  record(event: {
    requestId: string;
    name: string;
    detail?: Record<string, unknown>;
  }): Promise<void>;
}
