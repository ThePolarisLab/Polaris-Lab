import {
  AthenaReasoningEngine,
  ReasoningContext,
  ReasoningRule,
  RecommendationPolicy,
} from "../../src/athena";

const rule: ReasoningRule = {
  id: "cash-risk",
  evaluate: () => [
    {
      id: "finding-cash-risk",
      title: "Customer payment risk is increasing",
      description: "Receivables are aging while exposure remains material.",
      domain: "finance",
      evidenceIds: ["invoice-age", "balance-growth"],
      impact: 0.95,
      urgency: 0.9,
    },
  ],
};

const policy: RecommendationPolicy = {
  recommend: (finding) => ({
    id: "recommendation-contact-customer",
    findingId: finding.id,
    action: "Contact the customer and review credit exposure.",
    rationale: "Early intervention reduces cash-flow risk.",
    expectedImpact: "Improved collection probability and controlled exposure.",
  }),
};

const context: ReasoningContext = {
  requestId: "req-60",
  organizationId: "mor-logistics",
  objective: "Identify the most important financial risk",
  generatedAt: new Date("2026-07-25T00:00:00Z"),
  evidence: [
    {
      id: "invoice-age",
      organizationId: "mor-logistics",
      domain: "finance",
      source: "QuickBooks",
      observedAt: new Date("2026-07-24T00:00:00Z"),
      summary: "Average invoice age increased.",
      strength: "strong",
      reliability: 0.95,
      completeness: 0.9,
    },
    {
      id: "balance-growth",
      organizationId: "mor-logistics",
      domain: "finance",
      source: "QuickBooks",
      observedAt: new Date("2026-07-24T00:00:00Z"),
      summary: "Outstanding balance grew.",
      strength: "strong",
      reliability: 0.9,
      completeness: 0.95,
    },
  ],
};

describe("Athena Reasoning Engine", () => {
  test("produces explainable, prioritized, actionable insights", () => {
    const result = new AthenaReasoningEngine([rule], [policy]).reason(context);

    expect(result.summary).toContain("1 executive insight");
    expect(result.insights).toHaveLength(1);
    expect(result.insights[0].priority).toBe("critical");
    expect(result.insights[0].confidence.level).toBe("high");
    expect(result.insights[0].confidence.score).toBeGreaterThan(0.8);
    expect(result.insights[0].recommendation?.action).toContain("Contact the customer");
    expect(result.insights[0].explanation).toContain("QuickBooks");
  });

  test("is deterministic for the same context", () => {
    const engine = new AthenaReasoningEngine([rule], [policy]);
    expect(engine.reason(context)).toEqual(engine.reason(context));
  });

  test("lowers confidence when referenced evidence is missing", () => {
    const result = new AthenaReasoningEngine([rule]).reason({
      ...context,
      evidence: [context.evidence[0]],
    });

    expect(result.insights[0].confidence.level).toBe("low");
    expect(result.insights[0].confidence.conflicts).toEqual([
      "Missing evidence: balance-growth",
    ]);
  });

  test("rejects evidence from another organization", () => {
    const engine = new AthenaReasoningEngine([rule]);
    expect(() =>
      engine.reason({
        ...context,
        evidence: [{ ...context.evidence[0], organizationId: "other-company" }],
      }),
    ).toThrow("belongs to another organization");
  });
});
