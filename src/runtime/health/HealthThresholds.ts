export interface HealthThresholds {
  readonly failureRate: readonly [number, number, number];
  readonly queueDepth: readonly [number, number, number];
  readonly retryRate: readonly [number, number, number];
  readonly timeoutRate: readonly [number, number, number];
  readonly executionP95Ms: readonly [number, number, number];
  readonly minimumThroughputPerMinute: readonly [number, number, number];
}

export const DEFAULT_HEALTH_THRESHOLDS: HealthThresholds = Object.freeze({
  failureRate: [0.01, 0.03, 0.05],
  queueDepth: [10, 25, 50],
  retryRate: [0.05, 0.15, 0.3],
  timeoutRate: [0.01, 0.05, 0.1],
  executionP95Ms: [1_000, 5_000, 15_000],
  minimumThroughputPerMinute: [1, 0.5, 0.1],
});
