import { Decision, DecisionEvidence, DecisionOption } from "../core";
import {
  DecisionEvaluationResult,
  EvidenceAssessment,
  EvidenceDirection,
  OptionScore,
  ScoringWeights,
} from "./EvaluationTypes";

const DEFAULT_WEIGHTS: ScoringWeights = {
  evidence: 0.4,
  benefits: 0.15,
  drawbacks: 0.1,
  risks: 0.2,
  constraints: 0.15,
};

export class DecisionEvaluationError extends Error {}

export class DecisionEvaluator {
  private readonly weights: ScoringWeights;
  private readonly now: () => Date;

  constructor(weights: Partial<ScoringWeights> = {}, now: () => Date = () => new Date()) {
    this.weights = { ...DEFAULT_WEIGHTS, ...weights };
    this.now = now;
    this.validateWeights(this.weights);
  }

  evaluate(decision: Decision): DecisionEvaluationResult {
    if (decision.options.length === 0) {
      throw new DecisionEvaluationError("A decision requires at least one option to evaluate.");
    }

    const scores = decision.options.map((option) => this.scoreOption(decision, option));
    scores.sort((a, b) => b.total - a.total || a.optionId.localeCompare(b.optionId));
    scores.forEach((score, index) => {
      score.rank = index + 1;
    });

    const topScore = scores[0]?.total;
    const tiedOptionIds = scores
      .filter((score) => Math.abs(score.total - topScore) < 0.000001)
      .map((score) => score.optionId);

    const warnings: string[] = [];
    if (tiedOptionIds.length > 1) {
      warnings.push(`Top score is tied across options: ${tiedOptionIds.join(", ")}.`);
    }
    if (scores.every((score) => score.evidenceAssessments.length === 0)) {
      warnings.push("No option has linked evidence; rankings rely on structural factors only.");
    }

    return {
      decisionId: decision.id,
      evaluatedAt: this.now(),
      scores,
      tiedOptionIds,
      warnings,
    };
  }

  private scoreOption(decision: Decision, option: DecisionOption): OptionScore {
    const linkedEvidence = option.evidenceIds
      .map((id) => decision.evidence.find((item) => item.id === id))
      .filter((item): item is DecisionEvidence => Boolean(item));

    const evidenceAssessments = linkedEvidence.map((evidence) =>
      this.assessEvidence(option, evidence),
    );
    const evidenceScore = this.average(
      evidenceAssessments.map((assessment) => assessment.weightedContribution),
    );
    const benefitsScore = this.normalizeCount(option.benefits.length, 5);
    const drawbacksScore = 1 - this.normalizeCount(option.drawbacks.length, 5);

    const risks = option.riskIds
      .map((id) => decision.risks.find((risk) => risk.id === id))
      .filter((risk): risk is NonNullable<typeof risk> => Boolean(risk));
    const riskScore = risks.length
      ? 1 - this.average(risks.map((risk) => risk.likelihood * risk.impact))
      : 1;

    const constraints = option.constraintIds
      .map((id) => decision.constraints.find((constraint) => constraint.id === id))
      .filter((constraint): constraint is NonNullable<typeof constraint> => Boolean(constraint));
    const mandatoryConstraints = constraints.filter((constraint) => constraint.mandatory).length;
    const constraintScore = 1 - this.normalizeCount(mandatoryConstraints, 3);

    const breakdown = {
      evidence: this.round(evidenceScore),
      benefits: this.round(benefitsScore),
      drawbacks: this.round(drawbacksScore),
      risks: this.round(riskScore),
      constraints: this.round(constraintScore),
    };

    const total = this.round(
      breakdown.evidence * this.weights.evidence +
        breakdown.benefits * this.weights.benefits +
        breakdown.drawbacks * this.weights.drawbacks +
        breakdown.risks * this.weights.risks +
        breakdown.constraints * this.weights.constraints,
    );

    const warnings: string[] = [];
    if (linkedEvidence.length === 0) warnings.push("No linked evidence.");
    if (mandatoryConstraints > 0) {
      warnings.push(`${mandatoryConstraints} mandatory constraint(s) require explicit review.`);
    }
    if (risks.some((risk) => risk.level === "critical")) {
      warnings.push("Option includes at least one critical risk.");
    }

    return {
      optionId: option.id,
      optionTitle: option.title,
      total,
      rank: 0,
      breakdown,
      evidenceAssessments,
      warnings,
      explanation: [
        `Evidence contribution: ${breakdown.evidence}.`,
        `Benefit contribution: ${breakdown.benefits}.`,
        `Risk resilience: ${breakdown.risks}.`,
        `Constraint fit: ${breakdown.constraints}.`,
      ],
    };
  }

  private assessEvidence(option: DecisionOption, evidence: DecisionEvidence): EvidenceAssessment {
    const direction = this.inferDirection(option, evidence);
    const relevance = this.clamp(this.metadataNumber(evidence, "relevance", 1));
    const quality = this.clamp(this.metadataNumber(evidence, "quality", evidence.confidence));
    const sign = direction === "supports" ? 1 : direction === "opposes" ? -1 : 0;
    const raw = sign * relevance * evidence.confidence * quality;
    const weightedContribution = this.round((raw + 1) / 2);

    return {
      evidenceId: evidence.id,
      optionId: option.id,
      direction,
      relevance,
      confidence: evidence.confidence,
      quality,
      weightedContribution,
      explanation: `${evidence.title} ${direction} ${option.title} with relevance ${relevance}, confidence ${evidence.confidence}, and quality ${quality}.`,
    };
  }

  private inferDirection(option: DecisionOption, evidence: DecisionEvidence): EvidenceDirection {
    const directions = evidence.metadata.optionDirections;
    if (directions && typeof directions === "object" && !Array.isArray(directions)) {
      const value = (directions as Record<string, unknown>)[option.id];
      if (value === "supports" || value === "opposes" || value === "neutral") return value;
    }
    return "supports";
  }

  private metadataNumber(evidence: DecisionEvidence, key: string, fallback: number): number {
    const value = evidence.metadata[key];
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }

  private validateWeights(weights: ScoringWeights): void {
    const values = Object.values(weights);
    if (values.some((value) => !Number.isFinite(value) || value < 0)) {
      throw new DecisionEvaluationError("Scoring weights must be finite non-negative numbers.");
    }
    const sum = values.reduce((total, value) => total + value, 0);
    if (Math.abs(sum - 1) > 0.000001) {
      throw new DecisionEvaluationError("Scoring weights must sum to 1.");
    }
  }

  private normalizeCount(count: number, saturation: number): number {
    return this.clamp(count / saturation);
  }

  private average(values: number[]): number {
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  }

  private clamp(value: number): number {
    return Math.min(1, Math.max(0, value));
  }

  private round(value: number): number {
    return Math.round(value * 10000) / 10000;
  }
}
