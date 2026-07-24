export type HealthThresholdTuple = readonly [number, number, number];

export interface HealthThresholds {
  readonly failureRate: HealthThresholdTuple;
  readonly queueDepth: HealthThresholdTuple;
  readonly retryRate: HealthThresholdTuple;
  readonly timeoutRate: HealthThresholdTuple;
  readonly executionP95Ms: HealthThresholdTuple;
  readonly minimumThroughputPerMinute: HealthThresholdTuple;
}

export const DEFAULT_HEALTH_THRESHOLDS: HealthThresholds = Object.freeze({
  failureRate: [0.01, 0.03, 0.05] as const,
  queueDepth: [10, 25, 50] as const,
  retryRate: [0.05, 0.15, 0.3] as const,
  timeoutRate: [0.01, 0.05, 0.1] as const,
  executionP95Ms: [1_000, 5_000, 15_000] as const,
  minimumThroughputPerMinute: [1, 0.5, 0.1] as const,
});
