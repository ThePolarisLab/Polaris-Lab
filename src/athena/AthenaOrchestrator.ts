import {
  ContextAssembler,
  DecisionEngine,
  ExecutionPlanner,
  IntentClassifier,
  MemoryService,
  ResponseBuilder,
  TelemetrySink,
} from "./ports";
import {
  AthenaRequest,
  AthenaResponse,
  AthenaTelemetry,
  ExecutionPlan,
  ReasoningStep,
} from "./types";

export interface AthenaDependencies {
  intentClassifier: IntentClassifier;
  executionPlanner: ExecutionPlanner;
  contextAssembler: ContextAssembler;
  decisionEngine: DecisionEngine;
  responseBuilder: ResponseBuilder;
  memoryService: MemoryService;
  telemetry?: TelemetrySink;
  clock?: () => number;
}

export class AthenaOrchestrator {
  private readonly clock: () => number;

  constructor(private readonly dependencies: AthenaDependencies) {
    this.clock = dependencies.clock ?? (() => Date.now());
  }

  async execute(request: AthenaRequest): Promise<AthenaResponse> {
    this.validateRequest(request);
    const startedAt = this.clock();
    let plan: ExecutionPlan | undefined;

    try {
      const intent = await this.dependencies.intentClassifier.classify(request);
      plan = await this.dependencies.executionPlanner.createPlan(request, intent);
      await this.record(request.id, "plan.created", { intent, steps: plan.steps.length });

      this.completeStep(plan, "validate-request");
      this.startStep(plan, "assemble-context");
      const context = await this.dependencies.contextAssembler.assemble(request, plan);
      this.completeStep(plan, "assemble-context");
      this.completeStep(plan, "retrieve-memory");

      this.startStep(plan, "evaluate-evidence");
      const decision = await this.dependencies.decisionEngine.decide(request, plan, context);
      this.completeStep(plan, "evaluate-evidence");
      this.completeStep(plan, "form-decision");

      this.startStep(plan, "build-response");
      const answer = await this.dependencies.responseBuilder.buildAnswer(
        request,
        decision,
        context,
      );
      this.completeStep(plan, "build-response");

      this.startStep(plan, "persist-outcome");
      await this.dependencies.memoryService.remember(request, decision);
      this.completeStep(plan, "persist-outcome");

      const telemetry = this.buildTelemetry(
        request.id,
        intent,
        plan,
        startedAt,
        "completed",
      );
      await this.record(request.id, "request.completed", { ...telemetry });

      return { requestId: request.id, answer, intent, plan, decision, telemetry };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown Athena error";
      if (plan) {
        const running = plan.steps.find((item) => item.status === "running");
        if (running) {
          running.status = "failed";
          running.completedAt = new Date();
          running.detail = message;
        }
      }
      await this.record(request.id, "request.failed", { error: message });
      throw error;
    }
  }

  private validateRequest(request: AthenaRequest): void {
    if (!request.id.trim()) throw new Error("Athena request id is required");
    if (!request.userId.trim()) throw new Error("Athena user id is required");
    if (!request.prompt.trim()) throw new Error("Athena prompt is required");
  }

  private startStep(plan: ExecutionPlan, id: string): void {
    const item = this.findStep(plan, id);
    if (item.status === "completed") return;
    item.status = "running";
    item.startedAt = new Date();
  }

  private completeStep(plan: ExecutionPlan, id: string): void {
    const item = this.findStep(plan, id);
    item.status = "completed";
    item.startedAt ??= new Date();
    item.completedAt = new Date();
  }

  private findStep(plan: ExecutionPlan, id: string): ReasoningStep {
    const item = plan.steps.find((candidate) => candidate.id === id);
    if (!item) throw new Error(`Execution plan is missing required step: ${id}`);
    return item;
  }

  private buildTelemetry(
    requestId: string,
    intent: AthenaResponse["intent"],
    plan: ExecutionPlan,
    startedAt: number,
    status: AthenaTelemetry["status"],
  ): AthenaTelemetry {
    return {
      requestId,
      intent,
      executionTimeMs: Math.max(0, this.clock() - startedAt),
      stepCount: plan.steps.length,
      completedSteps: plan.steps.filter((item) => item.status === "completed").length,
      status,
    };
  }

  private async record(
    requestId: string,
    name: string,
    detail?: Record<string, unknown>,
  ): Promise<void> {
    await this.dependencies.telemetry?.record({ requestId, name, detail });
  }
}
