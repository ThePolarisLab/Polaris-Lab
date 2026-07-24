import { IMetricsProvider } from "../../src/runtime/metrics/IMetricsProvider";
import { MetricsSnapshot } from "../../src/runtime/metrics/MetricsSnapshot";
import { HealthMonitor } from "../../src/runtime/health/HealthMonitor";
import { HealthStatus } from "../../src/runtime/health/HealthStatus";

const histogram = Object.freeze({ count: 0, min: 0, max: 0, average: 0, p50: 0, p95: 0, p99: 0 });

function metrics(overrides: Partial<MetricsSnapshot> = {}): MetricsSnapshot {
  return Object.freeze({
    timestamp: new Date("2026-07-24T00:00:00Z"), created: 100, validated: 100, queued: 100,
    dispatched: 100, started: 100, succeeded: 100, failed: 0, cancelled: 0, retries: 0,
    timedOut: 0, completed: 100, queueDepth: 0, activeWorkers: 0, successRate: 1,
    failureRate: 0, throughputPerMinute: 10, queueDurationMs: histogram,
    dispatchDurationMs: histogram, executionDurationMs: histogram, ...overrides,
  });
}

class StaticMetrics implements IMetricsProvider {
  constructor(private current: MetricsSnapshot) {}
  snapshot(): MetricsSnapshot { return this.current; }
  set(next: MetricsSnapshot): void { this.current = next; }
}

describe("HealthMonitor", () => {
  it("reports healthy when all metrics are within thresholds", () => {
    const monitor = new HealthMonitor(new StaticMetrics(metrics()));
    expect(monitor.status()).toBe(HealthStatus.Healthy);
    expect(monitor.isHealthy()).toBe(true);
    expect(monitor.alerts()).toEqual([]);
  });

  it("selects the most severe active condition", () => {
    const monitor = new HealthMonitor(new StaticMetrics(metrics({ failureRate: 0.03, queueDepth: 50 })));
    const snapshot = monitor.snapshot();
    expect(snapshot.status).toBe(HealthStatus.Critical);
    expect(snapshot.alerts.map((alert) => alert.category)).toEqual(["failures", "queue"]);
    expect(monitor.isCritical()).toBe(true);
  });

  it("detects retry storms, timeout pressure, latency, and low throughput", () => {
    const slow = Object.freeze({ ...histogram, count: 10, p95: 20_000 });
    const monitor = new HealthMonitor(new StaticMetrics(metrics({ retries: 30, timedOut: 10,
      executionDurationMs: slow, throughputPerMinute: 0.05 })));
    expect(monitor.snapshot().alerts.map((alert) => alert.category)).toEqual([
      "retries", "timeouts", "latency", "throughput",
    ]);
  });

  it("recovers when the underlying metrics recover", () => {
    const provider = new StaticMetrics(metrics({ queueDepth: 60 }));
    const monitor = new HealthMonitor(provider);
    expect(monitor.status()).toBe(HealthStatus.Critical);
    provider.set(metrics());
    expect(monitor.status()).toBe(HealthStatus.Healthy);
  });

  it("returns frozen snapshots and alerts", () => {
    const snapshot = new HealthMonitor(new StaticMetrics(metrics({ queueDepth: 10 }))).snapshot();
    expect(Object.isFrozen(snapshot)).toBe(true);
    expect(Object.isFrozen(snapshot.alerts)).toBe(true);
    expect(Object.isFrozen(snapshot.alerts[0])).toBe(true);
  });
});
