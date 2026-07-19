import {
  ContextAssembler,
  DecisionEngine,
  MemoryService,
  ResponseBuilder,
} from "./ports";
import {
  AthenaContext,
  AthenaDecision,
  AthenaRequest,
  ExecutionPlan,
} from "./types";

export class EmptyContextAssembler implements ContextAssembler {
  async assemble(
    request: AthenaRequest,
    _plan: ExecutionPlan,
  ): Promise<AthenaContext> {
    return {
      workContext: {
        project: request.metadata?.project,
        organization: request.metadata?.organization,
        priority: request.metadata?.priority ?? "normal",
      },
      memory: {},
      knowledge: {},
    };
  }
}

export class BaselineDecisionEngine implements DecisionEngine {
  async decide(
    request: AthenaRequest,
    plan: ExecutionPlan,
    context: AthenaContext,
  ): Promise<AthenaDecision> {
    const hasScopedContext = Boolean(
      context.workContext.project || context.workContext.organization,
    );

    return {
      objective: plan.objective,
      reasoning: [
        `Classified the request as ${plan.intent}.`,
        "Created an explicit execution plan before producing a response.",
        "Evaluated the currently available work context, memory, and knowledge.",
      ],
      evidence: [],
      assumptions: hasScopedContext
        ? []
        : ["No project or organization scope was supplied with the request."],
      missingInformation: [
        "A production reasoning provider has not yet been connected.",
        "Executive Memory and the Knowledge Graph currently use empty adapters.",
      ],
      confidence: 0.35,
      nextActions: [
        `Connect evidence providers for the ${plan.intent} intent.`,
        "Replace baseline adapters with production implementations.",
      ],
    };
  }
}

export class ExecutiveResponseBuilder implements ResponseBuilder {
  async buildAnswer(
    request: AthenaRequest,
    decision: AthenaDecision,
    _context: AthenaContext,
  ): Promise<string> {
    const action = decision.nextActions[0] ?? "Gather additional context.";
    return `Athena processed “${request.prompt}”. Recommended next action: ${action}`;
  }
}

export class InMemoryDecisionStore implements MemoryService {
  private readonly decisions = new Map<string, AthenaDecision>();

  async remember(request: AthenaRequest, decision: AthenaDecision): Promise<void> {
    this.decisions.set(request.id, structuredClone(decision));
  }

  get(requestId: string): AthenaDecision | undefined {
    const decision = this.decisions.get(requestId);
    return decision ? structuredClone(decision) : undefined;
  }

  size(): number {
    return this.decisions.size;
  }
}
