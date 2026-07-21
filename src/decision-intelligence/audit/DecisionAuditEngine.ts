import { Decision } from "../core";
import { DecisionEvaluationResult } from "../evaluation";
import { DecisionRecommendationResult } from "../recommendation";
import { DecisionAuditRecord, EvidenceTrace } from "./DecisionAuditTypes";

export class DecisionAuditError extends Error {}

export class DecisionAuditEngine {
  build(
    decision: Decision,
    evaluation: DecisionEvaluationResult,
    recommendation: DecisionRecommendationResult,
  ): DecisionAuditRecord {
    this.validate(decision, evaluation, recommendation);

    const selectedScore = recommendation.recommendedOptionId
      ? evaluation.scores.find((score) => score.optionId === recommendation.recommendedOptionId)
      : [...evaluation.scores].sort(
          (a, b) => a.rank - b.rank || b.total - a.total || a.optionId.localeCompare(b.optionId),
        )[0];

    const evidenceTrace: EvidenceTrace[] = (selectedScore?.evidenceAssessments ?? [])
      .map((assessment) => ({
        evidenceId: assessment.evidenceId,
        optionId: assessment.optionId,
        direction: assessment.direction,
        weightedContribution: assessment.weightedContribution,
        explanation: assessment.explanation,
      }))
      .sort(
        (a, b) =>
          b.weightedContribution - a.weightedContribution ||
          a.evidenceId.localeCompare(b.evidenceId),
      );

    const stablePayload = {
      decisionId: decision.id,
      evaluation: evaluation.scores
        .map((score) => ({
          optionId: score.optionId,
          total: score.total,
          rank: score.rank,
          breakdown: score.breakdown,
          evidence: score.evidenceAssessments
            .map((item) => ({
              evidenceId: item.evidenceId,
              direction: item.direction,
              contribution: item.weightedContribution,
            }))
            .sort((a, b) => a.evidenceId.localeCompare(b.evidenceId)),
        }))
        .sort((a, b) => a.optionId.localeCompare(b.optionId)),
      recommendation: {
        status: recommendation.status,
        optionId: recommendation.recommendedOptionId,
        confidence: recommendation.confidence,
        rationale: recommendation.rationale,
        warnings: recommendation.warnings,
      },
    };

    return {
      decisionId: decision.id,
      recommendationStatus: recommendation.status,
      selectedOptionId: recommendation.recommendedOptionId,
      selectedOptionTitle: recommendation.recommendedOptionTitle,
      confidence: recommendation.confidence,
      generatedAt: recommendation.generatedAt,
      evaluationTimestamp: evaluation.evaluatedAt,
      evidenceTrace,
      alternatives: [...recommendation.tradeOffs],
      rationale: [...recommendation.rationale],
      warnings: [...recommendation.warnings],
      replayFingerprint: this.fingerprint(this.stableStringify(stablePayload)),
      deterministic: true,
    };
  }

  private validate(
    decision: Decision,
    evaluation: DecisionEvaluationResult,
    recommendation: DecisionRecommendationResult,
  ): void {
    if (decision.id !== evaluation.decisionId || decision.id !== recommendation.decisionId) {
      throw new DecisionAuditError(
        "Decision, evaluation, and recommendation must reference the same decision.",
      );
    }
    if (
      recommendation.recommendedOptionId &&
      !decision.options.some((option) => option.id === recommendation.recommendedOptionId)
    ) {
      throw new DecisionAuditError("Recommendation references an unknown decision option.");
    }
  }

  private stableStringify(value: unknown): string {
    if (Array.isArray(value)) {
      return `[${value.map((item) => this.stableStringify(item)).join(",")}]`;
    }
    if (value && typeof value === "object") {
      const record = value as Record<string, unknown>;
      return `{${Object.keys(record)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${this.stableStringify(record[key])}`)
        .join(",")}}`;
    }
    return JSON.stringify(value);
  }

  private fingerprint(value: string): string {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return `fnv1a-${(hash >>> 0).toString(16).padStart(8, "0")}`;
  }
}
