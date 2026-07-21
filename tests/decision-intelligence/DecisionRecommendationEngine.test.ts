import {
  Decision,
  DecisionEvaluationResult,
  DecisionRecommendationEngine,
  DecisionRecommendationError,
} from "../../src/decision-intelligence";

const fixedNow = new Date("2026-07-21T12:00:00Z");

function decision(): Decision {
  return {
    id: "decision-1",
    title: "Choose storage",
    question: "Which storage option should Polaris use?",
    status: "evaluating",
    options: [
      {
        id: "option-a",
        title: "PostgreSQL",
        description: "Relational storage",
        benefits: [],
        drawbacks: [],
        evidenceIds: ["evidence-1"],
        constraintIds: [],
        riskIds: [],
        metadata: {},
      },
      {
        id: "option-b",
        title: "Document Store",
        description: "Document storage",
        benefits: [],
        drawbacks: [],
        evidenceIds: ["evidence-2"],
        constraintIds: [],
        riskIds: [],
        metadata: {},
      },
    ],
    evidence: [],
    constraints: [],
    risks: [],
    tags: [],
    metadata: {},
    version: 1,
    createdAt: fixedNow,
    updatedAt: fixedNow,
  };
}

function evaluation(overrides: Partial<DecisionEvaluationResult> = {}): DecisionEvaluationResult {
  return {
    decisionId: "decision-1",
    evaluatedAt: fixedNow,
    tiedOptionIds: ["option-a"],
    warnings: [],
    scores: [
      {
        optionId: "option-a",
        optionTitle: "PostgreSQL",
        total: 0.82,
        rank: 1,
        breakdown: {
          evidence: 0.9,
          benefits: 0.8,
          drawbacks: 0.7,
          risks: 0.85,
          constraints: 0.9,
        },
        evidenceAssessments: [
          {
            evidenceId: "evidence-1",
            optionId: "option-a",
            direction: "supports",
            relevance: 1,
            confidence: 0.9,
            quality: 0.9,
            weightedContribution: 0.905,
            explanation: "Strong operational evidence.",
          },
        ],
        warnings: [],
        explanation: [],
      },
      {
        optionId: "option-b",
        optionTitle: "Document Store",
        total: 0.66,
        rank: 2,
        breakdown: {
          evidence: 0.6,
          benefits: 0.75,
          drawbacks: 0.8,
          risks: 0.65,
          constraints: 0.7,
        },
        evidenceAssessments: [
          {
            evidenceId: "evidence-2",
            optionId: "option-b",
            direction: "supports",
            relevance: 0.8,
            confidence: 0.7,
            quality: 0.7,
            weightedContribution: 0.696,
            explanation: "Moderate flexibility evidence.",
          },
        ],
        warnings: [],
        explanation: [],
      },
    ],
    ...overrides,
  };
}

describe("DecisionRecommendationEngine", () => {
  test("recommends a decisive top option with explainable trade-offs", () => {
    const result = new DecisionRecommendationEngine({}, () => fixedNow).generate(
      decision(),
      evaluation(),
    );

    expect(result.status).toBe("recommended");
    expect(result.recommendedOptionId).toBe("option-a");
    expect(result.confidence).toBeGreaterThan(0.5);
    expect(result.tradeOffs).toHaveLength(1);
    expect(result.tradeOffs[0].scoreDelta).toBe(0.16);
    expect(result.tradeOffs[0].advantages.length).toBeGreaterThan(0);
  });

  test("requires review when top options are tied", () => {
    const tied = evaluation({
      tiedOptionIds: ["option-a", "option-b"],
      scores: evaluation().scores.map((score) => ({ ...score, total: 0.75 })),
    });

    const result = new DecisionRecommendationEngine({}, () => fixedNow).generate(
      decision(),
      tied,
    );

    expect(result.status).toBe("review_required");
    expect(result.recommendedOptionId).toBeUndefined();
    expect(result.warnings.join(" ")).toMatch(/tie/i);
  });

  test("reports insufficient evidence instead of fabricating certainty", () => {
    const noEvidence = evaluation({
      scores: evaluation().scores.map((score) => ({
        ...score,
        evidenceAssessments: [],
        warnings: ["No linked evidence."],
      })),
    });

    const result = new DecisionRecommendationEngine({}, () => fixedNow).generate(
      decision(),
      noEvidence,
    );

    expect(result.status).toBe("insufficient_evidence");
    expect(result.recommendedOptionId).toBeUndefined();
  });

  test("rejects mismatched evaluations and invalid policies", () => {
    expect(() =>
      new DecisionRecommendationEngine().generate(
        decision(),
        evaluation({ decisionId: "other-decision" }),
      ),
    ).toThrow(DecisionRecommendationError);

    expect(() =>
      new DecisionRecommendationEngine({ minimumScore: 1.2 }),
    ).toThrow(DecisionRecommendationError);
  });
});
