import { CreateDecisionInput, Decision, DecisionOption } from "./Decision";

export class DecisionValidator {
  validateCreate(input: CreateDecisionInput): void {
    if (!input.title.trim()) throw new Error("Decision title is required");
    if (!input.question.trim()) throw new Error("Decision question is required");
  }

  validate(decision: Decision): void {
    this.validateCreate(decision);
    if (!decision.id.trim()) throw new Error("Decision id is required");
    if (decision.version < 1) throw new Error("Decision version must be at least 1");

    const ids = new Set<string>();
    for (const option of decision.options) this.assertUnique(ids, option.id, "option");
    for (const evidence of decision.evidence) {
      this.assertUnique(ids, evidence.id, "evidence");
      this.assertProbability(evidence.confidence, "Evidence confidence");
    }
    for (const constraint of decision.constraints) this.assertUnique(ids, constraint.id, "constraint");
    for (const risk of decision.risks) {
      this.assertUnique(ids, risk.id, "risk");
      this.assertProbability(risk.likelihood, "Risk likelihood");
      this.assertProbability(risk.impact, "Risk impact");
    }

    for (const option of decision.options) this.validateOptionReferences(decision, option);
    if (decision.recommendation) {
      this.assertProbability(decision.recommendation.confidence, "Recommendation confidence");
      if (!decision.options.some((option) => option.id === decision.recommendation?.optionId)) {
        throw new Error("Recommendation must reference an existing option");
      }
    }
  }

  private validateOptionReferences(decision: Decision, option: DecisionOption): void {
    const evidenceIds = new Set(decision.evidence.map((item) => item.id));
    const constraintIds = new Set(decision.constraints.map((item) => item.id));
    const riskIds = new Set(decision.risks.map((item) => item.id));
    if (option.evidenceIds.some((id) => !evidenceIds.has(id))) throw new Error("Option references unknown evidence");
    if (option.constraintIds.some((id) => !constraintIds.has(id))) throw new Error("Option references unknown constraint");
    if (option.riskIds.some((id) => !riskIds.has(id))) throw new Error("Option references unknown risk");
  }

  private assertUnique(ids: Set<string>, id: string, label: string): void {
    if (!id.trim()) throw new Error(`${label} id is required`);
    if (ids.has(id)) throw new Error(`Duplicate decision component id: ${id}`);
    ids.add(id);
  }

  private assertProbability(value: number, label: string): void {
    if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error(`${label} must be between 0 and 1`);
  }
}
