import {
  AthenaReasoningResult,
  ConfidenceAssessment,
  ExecutiveInsight,
  Finding,
  InsightPriority,
  ReasoningContext,
  ReasoningEvidence,
  ReasoningRule,
  RecommendationPolicy,
} from "./contracts";

const clamp = (value: number): number => Math.max(0, Math.min(1, value));

const strengthWeight: Record<ReasoningEvidence["strength"], number> = {
  weak: 0.35,
  moderate: 0.65,
  strong: 1,
};

export class AthenaReasoningEngine {
  constructor(
    private readonly rules: ReasoningRule[],
    private readonly recommendationPolicies: RecommendationPolicy[] = [],
  ) {}

  reason(context: ReasoningContext): AthenaReasoningResult {
    this.validateContext(context);

    const findings = this.rules
      .flatMap((rule) => rule.evaluate(context))
      .map((finding) => this.normalizeFinding(finding))
      .sort((left, right) => left.id.localeCompare(right.id));

    const insights = findings
      .map((finding) => this.buildInsight(finding, context.evidence))
      .sort((left, right) => {
        const priorityDifference = this.priorityRank(right.priority) - this.priorityRank(left.priority);
        if (priorityDifference !== 0) return priorityDifference;
        const confidenceDifference = right.confidence.score - left.confidence.score;
        if (confidenceDifference !== 0) return confidenceDifference;
        return left.finding.id.localeCompare(right.finding.id);
      });

    return {
      requestId: context.requestId,
      organizationId: context.organizationId,
      objective: context.objective,
      generatedAt: context.generatedAt,
      summary: this.summarize(insights),
      insights,
    };
  }

  private buildInsight(finding: Finding, allEvidence: ReasoningEvidence[]): ExecutiveInsight {
    const evidence = allEvidence
      .filter((item) => finding.evidenceIds.includes(item.id))
      .sort((left, right) => left.id.localeCompare(right.id));

    const confidence = this.assessConfidence(finding, evidence);
    const priority = this.assessPriority(finding, confidence);
    const recommendation = this.recommendationPolicies
      .map((policy) => policy.recommend(finding, evidence))
      .find((candidate) => candidate !== undefined);

    return {
      finding,
      priority,
      confidence,
      evidence,
      recommendation,
      explanation: this.explain(finding, evidence, confidence),
    };
  }

  private assessConfidence(finding: Finding, evidence: ReasoningEvidence[]): ConfidenceAssessment {
    if (evidence.length === 0) {
      return {
        score: 0,
        level: "low",
        reasons: ["No supporting evidence was available."],
        conflicts: finding.evidenceIds.map((id) => `Missing evidence: ${id}`),
      };
    }

    const evidenceScores = evidence.map((item) =>
      clamp(strengthWeight[item.strength] * clamp(item.reliability) * clamp(item.completeness)),
    );
    const average = evidenceScores.reduce((sum, score) => sum + score, 0) / evidenceScores.length;
    const coverage = evidence.length / Math.max(1, finding.evidenceIds.length);
    const score = Number(clamp(average * coverage).toFixed(4));
    const conflicts = finding.evidenceIds
      .filter((id) => !evidence.some((item) => item.id === id))
      .map((id) => `Missing evidence: ${id}`);

    return {
      score,
      level: score >= 0.75 ? "high" : score >= 0.45 ? "medium" : "low",
      reasons: [
        `${evidence.length} supporting evidence item(s) evaluated.`,
        `Evidence coverage is ${Math.round(coverage * 100)}%.`,
      ],
      conflicts,
    };
  }

  private assessPriority(finding: Finding, confidence: ConfidenceAssessment): InsightPriority {
    const score = clamp((clamp(finding.impact) * 0.55 + clamp(finding.urgency) * 0.45) * (0.5 + confidence.score * 0.5));
    if (score >= 0.85) return "critical";
    if (score >= 0.65) return "high";
    if (score >= 0.4) return "medium";
    if (score >= 0.2) return "low";
    return "informational";
  }

  private explain(
    finding: Finding,
    evidence: ReasoningEvidence[],
    confidence: ConfidenceAssessment,
  ): string {
    const sources = Array.from(new Set(evidence.map((item) => item.source))).sort();
    const sourceText = sources.length > 0 ? sources.join(", ") : "no verified sources";
    return `${finding.title}: ${finding.description} Supported by ${evidence.length} evidence item(s) from ${sourceText}. Confidence is ${Math.round(confidence.score * 100)}%.`;
  }

  private summarize(insights: ExecutiveInsight[]): string {
    if (insights.length === 0) return "No executive insights were produced.";
    const urgent = insights.filter((item) => item.priority === "critical" || item.priority === "high").length;
    return `${insights.length} executive insight(s) produced; ${urgent} require high or critical attention.`;
  }

  private normalizeFinding(finding: Finding): Finding {
    return {
      ...finding,
      impact: clamp(finding.impact),
      urgency: clamp(finding.urgency),
      evidenceIds: Array.from(new Set(finding.evidenceIds)).sort(),
    };
  }

  private validateContext(context: ReasoningContext): void {
    if (!context.requestId.trim()) throw new Error("requestId is required");
    if (!context.organizationId.trim()) throw new Error("organizationId is required");
    if (!context.objective.trim()) throw new Error("objective is required");

    const foreignEvidence = context.evidence.find(
      (item) => item.organizationId !== context.organizationId,
    );
    if (foreignEvidence) {
      throw new Error(`Evidence ${foreignEvidence.id} belongs to another organization`);
    }

    const ids = new Set<string>();
    for (const item of context.evidence) {
      if (ids.has(item.id)) throw new Error(`Duplicate evidence id: ${item.id}`);
      ids.add(item.id);
    }
  }

  private priorityRank(priority: InsightPriority): number {
    return {
      informational: 0,
      low: 1,
      medium: 2,
      high: 3,
      critical: 4,
    }[priority];
  }
}
