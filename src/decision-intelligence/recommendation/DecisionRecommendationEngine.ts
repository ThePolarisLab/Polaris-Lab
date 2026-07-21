import { Decision } from "../core";
import { DecisionEvaluationResult, OptionScore } from "../evaluation";
import {
  DecisionRecommendationResult,
  OptionTradeOff,
  RecommendationPolicy,
  TradeOffDimension,
} from "./RecommendationTypes";

const DEFAULT_POLICY: RecommendationPolicy = {
  minimumScore: 0.55,
  minimumMargin: 0.05,
  maximumTopOptionWarnings: 1,
  requireEvidence: true,
};

export class DecisionRecommendationError extends Error {}

export class DecisionRecommendationEngine {
  private readonly policy: RecommendationPolicy;
  private readonly now: () => Date;

  constructor(
    policy: Partial<RecommendationPolicy> = {},
    now: () => Date = () => new Date(),
  ) {
    this.policy = { ...DEFAULT_POLICY, ...policy };
    this.now = now;
    this.validatePolicy(this.policy);
  }

  generate(
    decision: Decision,
    evaluation: DecisionEvaluationResult,
  ): DecisionRecommendationResult {
    if (decision.id !== evaluation.decisionId) {
      throw new DecisionRecommendationError(
        "Evaluation result does not belong to the supplied decision.",
      );
    }
    if (evaluation.scores.length === 0) {
      throw new DecisionRecommendationError(
        "Evaluation result must contain at least one option score.",
      );
    }

    const knownOptionIds = new Set(decision.options.map((option) => option.id));
    if (evaluation.scores.some((score) => !knownOptionIds.has(score.optionId))) {
      throw new DecisionRecommendationError(
        "Evaluation result references an unknown decision option.",
      );
    }

    const scores = [...evaluation.scores].sort(
      (a, b) => a.rank - b.rank || b.total - a.total || a.optionId.localeCompare(b.optionId),
    );
    const top = scores[0];
    const runnerUp = scores[1];
    const margin = runnerUp ? this.round(top.total - runnerUp.total) : top.total;
    const warnings = [...evaluation.warnings];
    const rationale: string[] = [
      `${top.optionTitle} is ranked first with a normalized score of ${top.total}.`,
      runnerUp
        ? `Its score advantage over ${runnerUp.optionTitle} is ${margin}.`
        : "It is the only evaluated option.",
      ...this.leadingDimensions(top),
    ];

    const evidenceMissing =
      top.evidenceAssessments.length === 0 ||
      top.warnings.some((warning) => warning.toLowerCase().includes("no linked evidence"));
    const tied = evaluation.tiedOptionIds.length > 1;
    const belowScore = top.total < this.policy.minimumScore;
    const narrowMargin = Boolean(runnerUp) && margin < this.policy.minimumMargin;
    const tooManyWarnings = top.warnings.length > this.policy.maximumTopOptionWarnings;

    let status: DecisionRecommendationResult["status"] = "recommended";
    if (this.policy.requireEvidence && evidenceMissing) {
      status = "insufficient_evidence";
      warnings.push("The highest-ranked option lacks sufficient linked evidence.");
    } else if (tied || belowScore || narrowMargin || tooManyWarnings) {
      status = "review_required";
      if (tied) warnings.push("A deterministic recommendation cannot break a top-score tie.");
      if (belowScore) warnings.push("The leading score is below the recommendation threshold.");
      if (narrowMargin) warnings.push("The leading option does not have a decisive score margin.");
      if (tooManyWarnings) warnings.push("The leading option has unresolved evaluation warnings.");
    }

    const confidence = this.confidence(top, margin, warnings.length, status);
    const tradeOffs = scores.slice(1).map((alternative) =>
      this.compare(top, alternative),
    );

    return {
      decisionId: decision.id,
      status,
      recommendedOptionId: status === "recommended" ? top.optionId : undefined,
      recommendedOptionTitle: status === "recommended" ? top.optionTitle : undefined,
      confidence,
      generatedAt: this.now(),
      rationale,
      tradeOffs,
      warnings: [...new Set([...top.warnings, ...warnings])],
    };
  }

  private compare(recommended: OptionScore, alternative: OptionScore): OptionTradeOff {
    const dimensions = (Object.keys(recommended.breakdown) as Array<keyof OptionScore["breakdown"]>)
      .map((dimension) => this.compareDimension(dimension, recommended, alternative));
    const advantages = dimensions
      .filter((item) => item.delta > 0.0001)
      .map((item) => item.interpretation);
    const disadvantages = dimensions
      .filter((item) => item.delta < -0.0001)
      .map((item) => item.interpretation);

    return {
      alternativeOptionId: alternative.optionId,
      alternativeOptionTitle: alternative.optionTitle,
      scoreDelta: this.round(recommended.total - alternative.total),
      dimensions,
      advantages,
      disadvantages,
    };
  }

  private compareDimension(
    dimension: keyof OptionScore["breakdown"],
    recommended: OptionScore,
    alternative: OptionScore,
  ): TradeOffDimension {
    const recommendedValue = recommended.breakdown[dimension];
    const alternativeValue = alternative.breakdown[dimension];
    const delta = this.round(recommendedValue - alternativeValue);
    const relation = delta > 0 ? "stronger" : delta < 0 ? "weaker" : "equal";
    return {
      dimension,
      recommendedValue,
      alternativeValue,
      delta,
      interpretation: `${recommended.optionTitle} is ${relation} than ${alternative.optionTitle} on ${dimension} by ${Math.abs(delta)}.`,
    };
  }

  private leadingDimensions(score: OptionScore): string[] {
    return (Object.entries(score.breakdown) as Array<[
      keyof OptionScore["breakdown"],
      number,
    ]>)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 2)
      .map(([dimension, value]) => `Its strongest evaluated dimension is ${dimension} at ${value}.`);
  }

  private confidence(
    top: OptionScore,
    margin: number,
    warningCount: number,
    status: DecisionRecommendationResult["status"],
  ): number {
    const evidenceCoverage = top.evidenceAssessments.length
      ? Math.min(1, top.evidenceAssessments.length / 3)
      : 0;
    const base = top.total * 0.55 + Math.min(1, margin * 4) * 0.25 + evidenceCoverage * 0.2;
    const warningPenalty = Math.min(0.3, warningCount * 0.05);
    const statusPenalty = status === "recommended" ? 0 : status === "review_required" ? 0.15 : 0.3;
    return this.round(Math.max(0, Math.min(1, base - warningPenalty - statusPenalty)));
  }

  private validatePolicy(policy: RecommendationPolicy): void {
    const bounded = [policy.minimumScore, policy.minimumMargin];
    if (bounded.some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
      throw new DecisionRecommendationError(
        "Recommendation score and margin thresholds must be between 0 and 1.",
      );
    }
    if (
      !Number.isInteger(policy.maximumTopOptionWarnings) ||
      policy.maximumTopOptionWarnings < 0
    ) {
      throw new DecisionRecommendationError(
        "maximumTopOptionWarnings must be a non-negative integer.",
      );
    }
  }

  private round(value: number): number {
    return Math.round(value * 10000) / 10000;
  }
}
