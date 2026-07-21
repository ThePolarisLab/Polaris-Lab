import {
  Decision,
  DecisionAuditEngine,
  DecisionAuditError,
  DecisionEvaluationResult,
  DecisionRecommendationEngine,
} from "../../src/decision-intelligence";

const fixedNow = new Date("2026-07-21T12:00:00Z");

function decision(): Decision {
  return {
    id: "decision-1",
    title: "Choose storage",
    question: "Which storage option should Polaris use?",
    status: "evaluating",
    options: [
      { id: "option-a", title: "PostgreSQL", description: "Relational", benefits: [], drawbacks: [], evidenceIds: ["evidence-1"], constraintIds: [], riskIds: [], metadata: {} },
      { id: "option-b", title: "Document Store", description: "Document", benefits: [], drawbacks: [], evidenceIds: [], constraintIds: [], riskIds: [], metadata: {} },
    ],
    evidence: [], constraints: [], risks: [], tags: [], metadata: {}, version: 1,
    createdAt: fixedNow, updatedAt: fixedNow,
  };
}

function evaluation(): DecisionEvaluationResult {
  return {
    decisionId: "decision-1", evaluatedAt: fixedNow, tiedOptionIds: ["option-a"], warnings: [],
    scores: [
      {
        optionId: "option-a", optionTitle: "PostgreSQL", total: 0.82, rank: 1,
        breakdown: { evidence: 0.9, benefits: 0.8, drawbacks: 0.7, risks: 0.85, constraints: 0.9 },
        evidenceAssessments: [{ evidenceId: "evidence-1", optionId: "option-a", direction: "supports", relevance: 1, confidence: 0.9, quality: 0.9, weightedContribution: 0.905, explanation: "Strong operational evidence." }],
        warnings: [], explanation: [],
      },
      {
        optionId: "option-b", optionTitle: "Document Store", total: 0.66, rank: 2,
        breakdown: { evidence: 0.6, benefits: 0.75, drawbacks: 0.8, risks: 0.65, constraints: 0.7 },
        evidenceAssessments: [], warnings: [], explanation: [],
      },
    ],
  };
}

describe("DecisionAuditEngine", () => {
  test("creates an explainable evidence-linked audit record", () => {
    const input = evaluation();
    const recommendation = new DecisionRecommendationEngine({}, () => fixedNow).generate(decision(), input);
    const result = new DecisionAuditEngine().build(decision(), input, recommendation);

    expect(result.selectedOptionId).toBe("option-a");
    expect(result.evidenceTrace[0].evidenceId).toBe("evidence-1");
    expect(result.alternatives).toHaveLength(1);
    expect(result.deterministic).toBe(true);
    expect(result.replayFingerprint).toMatch(/^fnv1a-/);
  });

  test("produces the same replay fingerprint for the same inputs", () => {
    const input = evaluation();
    const recommendation = new DecisionRecommendationEngine({}, () => fixedNow).generate(decision(), input);
    const engine = new DecisionAuditEngine();

    expect(engine.build(decision(), input, recommendation).replayFingerprint).toBe(
      engine.build(decision(), input, recommendation).replayFingerprint,
    );
  });

  test("rejects mismatched decision artifacts", () => {
    const input = evaluation();
    const recommendation = new DecisionRecommendationEngine({}, () => fixedNow).generate(decision(), input);
    expect(() => new DecisionAuditEngine().build({ ...decision(), id: "other" }, input, recommendation)).toThrow(DecisionAuditError);
  });
});
