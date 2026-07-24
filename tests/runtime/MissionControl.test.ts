import { HealthStatus } from "../../src/runtime/health/HealthStatus";
import { IHealthProvider } from "../../src/runtime/health/IHealthProvider";
import { IMetricsProvider } from "../../src/runtime/metrics/IMetricsProvider";
import { MetricsSnapshot } from "../../src/runtime/metrics/MetricsSnapshot";
import { MissionControl } from "../../src/runtime/mission-control/MissionControl";
import { Scheduler } from "../../src/runtime/scheduler/Scheduler";
import { WorkerRegistry } from "../../src/runtime/sdk/WorkerRegistry";
import { defineWorker } from "../../src/runtime/sdk/WorkerFactory";

const histogram = Object.freeze({ count: 0, min: 0, max: 0, average: 0, p50: 0, p95: 0, p99: 0 });
const metricsSnapshot: MetricsSnapshot = Object.freeze({
  timestamp: new Date("2026-07-24T03:30:00.000Z"),
  created: 4,
  validated: 4,
  queued: 4,
  dispatched: 3,
  started: 3,
  succeeded: 2,
  failed: 1,
  cancelled: 0,
  retries: 1,
  timedOut: 0,
  completed: 3,
  queueDepth: 1,
  activeWorkers: 0,
  successRate: 2 / 3,
  failureRate: 1 / 3,
  throughputPerMinute: 3,
  queueDurationMs: histogram,
  dispatchDurationMs: histogram,
  executionDurationMs: histogram,
});

const metrics: IMetricsProvider = { snapshot: () => metricsSnapshot };
const health: IHealthProvider = {
  status: () => HealthStatus.Degraded,
  snapshot: () => Object.freeze({
    timestamp: new Date("2026-07-24T03:30:00.000Z"),
    status: HealthStatus.Degraded,
    alerts: Object.freeze([Object.freeze({
      id: "queue.degraded",
      category: "queue" as const,
      severity: HealthStatus.Degraded,
      message: "Queue pressure detected.",
      observedValue: 12,
      threshold: 10,
      suggestedAction: "Inspect dispatch capacity.",
    })]),
  }),
  alerts() { return this.snapshot().alerts; },
  isHealthy: () => false,
  isCritical: () => false,
};

describe("MissionControl", () => {
  it("aggregates runtime workers, scheduling, metrics, and health", () => {
    const registry = new WorkerRegistry();
    registry.register(defineWorker({
      name: "alpha-worker",
      version: "1.2.3",
      description: "Mission Control test worker.",
      handler: () => "done",
    }));
    const scheduler = new Scheduler();
    scheduler.enqueue({ workerName: "alpha-worker" });

    const control = new MissionControl(
      registry,
      scheduler,
      metrics,
      health,
      "0.1.0-alpha",
      () => new Date("2026-07-24T04:00:00.000Z"),
    );
    const snapshot = control.snapshot();

    expect(snapshot.timestamp.toISOString()).toBe("2026-07-24T04:00:00.000Z");
    expect(snapshot.runtimeVersion).toBe("0.1.0-alpha");
    expect(snapshot.health).toBe(HealthStatus.Degraded);
    expect(snapshot.queueDepth).toBe(1);
    expect(snapshot.metrics.completed).toBe(3);
    expect(snapshot.workers).toEqual([{ name: "alpha-worker", version: "1.2.3", description: "Mission Control test worker." }]);
    expect(snapshot.alerts[0].category).toBe("queue");
  });

  it("returns frozen operational snapshots", () => {
    const snapshot = new MissionControl(
      new WorkerRegistry(),
      new Scheduler(),
      metrics,
      health,
    ).snapshot();

    expect(Object.isFrozen(snapshot)).toBe(true);
    expect(Object.isFrozen(snapshot.workers)).toBe(true);
    expect(Object.isFrozen(snapshot.alerts)).toBe(true);
  });
});
