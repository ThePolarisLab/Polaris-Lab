import { HistogramSnapshot } from "./MetricHistogram";

export interface MetricsSnapshot {
  readonly timestamp: Date;
  readonly created: number;
  readonly validated: number;
  readonly queued: number;
  readonly dispatched: number;
  readonly started: number;
  readonly succeeded: number;
  readonly failed: number;
  readonly cancelled: number;
  readonly retries: number;
  readonly timedOut: number;
  readonly completed: number;
  readonly queueDepth: number;
  readonly activeWorkers: number;
  readonly successRate: number;
  readonly failureRate: number;
  readonly throughputPerMinute: number;
  readonly queueDurationMs: HistogramSnapshot;
  readonly dispatchDurationMs: HistogramSnapshot;
  readonly executionDurationMs: HistogramSnapshot;
}
