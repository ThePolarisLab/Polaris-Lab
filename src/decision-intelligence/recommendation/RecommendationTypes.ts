import { OptionScore } from "../evaluation";

export type RecommendationStatus =
  | "recommended"
  | "review_required"
  | "insufficient_evidence";

export interface RecommendationPolicy {
  minimumScore: number;
  minimumMargin: number;
  maximumTopOptionWarnings: number;
  requireEvidence: boolean;
}

export interface TradeOffDimension {
  dimension: keyof OptionScore["breakdown"];
  recommendedValue: number;
  alternativeValue: number;
  delta: number;
  interpretation: string;
}

export interface OptionTradeOff {
  alternativeOptionId: string;
  alternativeOptionTitle: string;
  scoreDelta: number;
  dimensions: TradeOffDimension[];
  advantages: string[];
  disadvantages: string[];
}

export interface DecisionRecommendationResult {
  decisionId: string;
  status: RecommendationStatus;
  recommendedOptionId?: string;
  recommendedOptionTitle?: string;
  confidence: number;
  generatedAt: Date;
  rationale: string[];
  tradeOffs: OptionTradeOff[];
  warnings: string[];
}
