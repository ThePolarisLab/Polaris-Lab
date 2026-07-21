import {
  Decision,
  DecisionEvaluationError,
  DecisionEvaluator,
} from "../../src/decision-intelligence";

const fixedNow = new Date("2026-07-21T12:00:00Z");

function buildDecision(): Decision {
  return {
    id: "decision-1",
    title: "Choose storage",
    question: "Which storage option should Polaris use?",
    status: "evaluating",
    options: [
      {
        id: "postgres",
        title: "PostgreSQL",
        description: "Relational persistence",
        benefits: ["Mature tooling", "Transactional consistency", "Operational familiarity"],
        drawbacks: ["Graph traversals require joins"],
        evidenceIds: ["latency", "operations"],
        constraintIds: [],
        riskIds: ["migration"],
        metadata: {},
      },
      {
        id: "graph",
        title: "Graph database",
        description: "Native graph persistence",
        benefits: ["Native traversals"],
        drawbacks: ["New operational platform", "Migration complexity"],
        evidenceIds: ["latency"],
        constraintIds: ["capacity"],
        riskIds: ["operations-risk"],
        metadata: {},
      },
    ],
    evidence: [
      {
        id: "latency",
        type: "metric",
        title: "Latency benchmark",
        summary: "PostgreSQL meets the current target",
        confidence: 0.9,
        metadata: {
          quality: 0.95,
          relevance: 1,
          optionDirections: { postgres: "supports", graph: "neutral" },
        },
      },
      {
        id: "operations",
        type: "expert_judgment",
        title: "Operations readiness",
        summary: "The team can operate PostgreSQL today",
        confidence: 0.8,
        metadata: { quality: 0.8, optionDirections: { postgres: "supports" } },
      },
    ],
    constraints: [
      {
        id: "capacity",
        type: "capacity",
        description: "No graph database operations capacity",
        mandatory: true,
        metadata: {},
      },
    ],
    risks: [
      {
        id: "migration",
        title: "Migration",
        description: "Moderate migration effort",
        likelihood: 0.3,
        impact: 0.4,
        level: "medium",
        metadata: {},
      },
      {
        id: "operations-risk",
        title: "Operations",
        description: "No production experience",
        likelihood: 0.8,
        impact: 0.9,
        level: "critical",
        metadata: {},
      },
    ],
    tags: [],
    metadata: {},
    version: 1,
    createdAt: fixedNow,
    updatedAt: fixedNow,
  };
}

describe("DecisionEvaluator", () => {
  test("ranks options deterministically with explainable breakdowns", () => {
    const result = new DecisionEvaluator({}, () => fixedNow).evaluate(buildDecision());

    expect(result.evaluatedAt).toEqual(fixedNow);
    expect(result.scores[0].optionId).toBe("postgres");
    expect(result.scores[0].rank).toBe(1);
    expect(result.scores[0].evidenceAssessments).toHaveLength(2);
    expect(result.scores[0].explanation).toHaveLength(4);
    expect(result.scores[1].warnings).toContain(
      "1 mandatory constraint(s) require explicit review.",
    );
    expect(result.scores[1].warnings).toContain("Option includes at least one critical risk.");
  });

  test("reports ties using stable option-id ordering", () => {
    const decision = buildDecision();
    decision.options = decision.options.map((option) => ({
      ...option,
      benefits: [],
      drawbacks: [],
      evidenceIds: [],
      constraintIds: [],
      riskIds: [],
    }));

    const result = new DecisionEvaluator({}, () => fixedNow).evaluate(decision);
    expect(result.scores.map((score) => score.optionId)).toEqual(["graph", "postgres"]);
    expect(result.tiedOptionIds).toEqual(["graph", "postgres"]);
    expect(result.warnings).toContain(
      "No option has linked evidence; rankings rely on structural factors only.",
    );
  });

  test("rejects missing options and invalid weight configurations", () => {
    const decision = buildDecision();
    decision.options = [];

    expect(() => new DecisionEvaluator().evaluate(decision)).toThrow(
      "at least one option",
    );
    expect(
      () => new DecisionEvaluator({ evidence: 0.9 }),
    ).toThrow(DecisionEvaluationError);
    expect(
      () => new DecisionEvaluator({ evidence: -0.1, benefits: 0.65 }),
    ).toThrow("non-negative");
  });

  test("uses evidence direction to reduce opposing evidence contribution", () => {
    const decision = buildDecision();
    decision.evidence[0].metadata.optionDirections = { postgres: "opposes" };
    decision.options = [decision.options[0]];

    const result = new DecisionEvaluator({}, () => fixedNow).evaluate(decision);
    const assessment = result.scores[0].evidenceAssessments[0];

    expect(assessment.direction).toBe("opposes");
    expect(assessment.weightedContribution).toBeLessThan(0.5);
  });
});
