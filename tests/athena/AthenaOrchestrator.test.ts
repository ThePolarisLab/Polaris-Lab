import assert from "node:assert/strict";
import test from "node:test";
import {
  AthenaOrchestrator,
  BaselineDecisionEngine,
  DefaultExecutionPlanner,
  DefaultIntentClassifier,
  EmptyContextAssembler,
  ExecutiveResponseBuilder,
  InMemoryDecisionStore,
} from "../../src/athena";

test("Athena classifies, plans, decides, responds, and remembers", async () => {
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

  assert.equal(response.intent, "finance");
  assert.equal(response.telemetry.status, "completed");
  assert.equal(response.telemetry.completedSteps, response.plan.steps.length);
  assert.equal(memory.size(), 1);
  assert.ok(memory.get("req-001"));
  assert.deepEqual(events, ["plan.created", "request.completed"]);
});

test("Athena rejects a blank prompt before execution", async () => {
  const orchestrator = new AthenaOrchestrator({
    intentClassifier: new DefaultIntentClassifier(),
    executionPlanner: new DefaultExecutionPlanner(),
    contextAssembler: new EmptyContextAssembler(),
    decisionEngine: new BaselineDecisionEngine(),
    responseBuilder: new ExecutiveResponseBuilder(),
    memoryService: new InMemoryDecisionStore(),
  });

  await assert.rejects(
    orchestrator.execute({
      id: "req-002",
      userId: "founder-001",
      prompt: "   ",
      timestamp: new Date(),
    }),
    /prompt is required/,
  );
});
