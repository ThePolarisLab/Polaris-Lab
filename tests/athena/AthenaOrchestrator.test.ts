import {
  AthenaOrchestrator,
  BaselineDecisionEngine,
  DefaultExecutionPlanner,
  DefaultIntentClassifier,
  EmptyContextAssembler,
  ExecutiveResponseBuilder,
  InMemoryDecisionStore,
} from "../../src/athena";

describe("Athena Orchestrator", () => {
  test("classifies, plans, decides, responds, and remembers", async () => {
    const memory = new InMemoryDecisionStore();
    const events: string[] = [];
    let now = 1_000;

    const orchestrator = new AthenaOrchestrator({
      intentClassifier: new DefaultIntentClassifier(),
      executionPlanner: new DefaultExecutionPlanner(),
      contextAssembler: new EmptyContextAssembler(),
      decisionEngine: new BaselineDecisionEngine(),
      responseBuilder: new ExecutiveResponseBuilder(),
      memoryService: memory,
      telemetry: {
        async record(event) {
          events.push(event.name);
        },
      },
      clock: () => (now += 5),
    });

    const response = await orchestrator.execute({
      id: "req-001",
      userId: "founder-001",
      prompt: "Analyze Mor Logistics cash flow",
      timestamp: new Date("2026-07-18T12:00:00Z"),
      metadata: { organization: "Mor Logistics", priority: "high" },
    });

    expect(response.intent).toBe("finance");
    expect(response.telemetry.status).toBe("completed");
    expect(response.telemetry.completedSteps).toBe(response.plan.steps.length);
    expect(memory.size()).toBe(1);
    expect(memory.get("req-001")).toBeDefined();
    expect(events).toEqual(["plan.created", "request.completed"]);
  });

  test("rejects a blank prompt before execution", async () => {
    const orchestrator = new AthenaOrchestrator({
      intentClassifier: new DefaultIntentClassifier(),
      executionPlanner: new DefaultExecutionPlanner(),
      contextAssembler: new EmptyContextAssembler(),
      decisionEngine: new BaselineDecisionEngine(),
      responseBuilder: new ExecutiveResponseBuilder(),
      memoryService: new InMemoryDecisionStore(),
    });

    await expect(
      orchestrator.execute({
        id: "req-002",
        userId: "founder-001",
        prompt: "   ",
        timestamp: new Date(),
      }),
    ).rejects.toThrow("prompt is required");
  });
});
