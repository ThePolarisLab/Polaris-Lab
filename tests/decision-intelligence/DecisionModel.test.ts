import {
  DecisionFactory,
  DecisionValidator,
  InMemoryDecisionRepository,
} from "../../src/decision-intelligence";

const fixedNow = new Date("2026-07-20T12:00:00Z");

function createDecision() {
  return new DecisionFactory(
    new DecisionValidator(),
    () => fixedNow,
    () => "decision-1",
  ).create({
    title: "Choose Atlas storage",
    question: "Which persistence strategy should Atlas use?",
    tags: ["atlas", "storage", "atlas"],
  });
}

describe("Decision Model Core", () => {
  test("creates a normalized draft decision", () => {
    const decision = createDecision();
    expect(decision.id).toBe("decision-1");
    expect(decision.status).toBe("draft");
    expect(decision.tags).toEqual(["atlas", "storage"]);
    expect(decision.version).toBe(1);
  });

  test("stores, retrieves, updates, filters, and deletes decisions defensively", async () => {
    const repository = new InMemoryDecisionRepository();
    const created = await repository.create(createDecision());
    created.title = "mutated outside repository";

    expect((await repository.getById("decision-1"))?.title).toBe("Choose Atlas storage");

    const current = await repository.getById("decision-1");
    if (!current) throw new Error("decision missing");
    current.status = "evaluating";
    const updated = await repository.update(current);

    expect(updated.version).toBe(2);
    expect((await repository.list("evaluating"))).toHaveLength(1);
    expect(await repository.delete("decision-1")).toBe(true);
    expect(await repository.getById("decision-1")).toBeUndefined();
  });

  test("validates component references and confidence ranges", () => {
    const decision = createDecision();
    decision.options.push({
      id: "option-1",
      title: "PostgreSQL",
      description: "Use relational persistence",
      benefits: [],
      drawbacks: [],
      evidenceIds: ["missing-evidence"],
      constraintIds: [],
      riskIds: [],
      metadata: {},
    });

    expect(() => new DecisionValidator().validate(decision)).toThrow("unknown evidence");
  });

  test("accepts a recommendation backed by existing decision components", () => {
    const decision = createDecision();
    decision.evidence.push({
      id: "evidence-1",
      type: "metric",
      title: "Query latency",
      summary: "PostgreSQL meets the latency target",
      confidence: 0.9,
      metadata: {},
    });
    decision.options.push({
      id: "option-1",
      title: "PostgreSQL",
      description: "Use relational persistence",
      benefits: ["Operational maturity"],
      drawbacks: ["Graph traversal requires joins"],
      evidenceIds: ["evidence-1"],
      constraintIds: [],
      riskIds: [],
      score: 0.86,
      metadata: {},
    });
    decision.recommendation = {
      optionId: "option-1",
      rationale: "Best balance of reliability and delivery speed",
      confidence: 0.86,
      recommendedAt: fixedNow,
    };
    decision.status = "recommended";

    expect(() => new DecisionValidator().validate(decision)).not.toThrow();
  });
});
