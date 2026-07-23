import { EventBus } from "../../src/runtime/events/EventBus";
import { RuntimeLifecycleEvent } from "../../src/runtime/lifecycle/RuntimeEvents";
import { WorkerState } from "../../src/runtime/lifecycle/WorkerState";
import { MetricCounter } from "../../src/runtime/metrics/MetricCounter";
import { MetricGauge } from "../../src/runtime/metrics/MetricGauge";
import { MetricHistogram } from "../../src/runtime/metrics/MetricHistogram";
import { MetricsCollector } from "../../src/runtime/metrics/MetricsCollector";

function lifecycleEvent(
  name: RuntimeLifecycleEvent["name"],
  state: WorkerState,
  timestampMs: number,
  executionId = "execution-1",
): RuntimeLifecycleEvent {
  return {
    id: `${name}-${executionId}`,
    name,
    executionId,
    workerName: "test-worker",
    state,
    timestamp: new Date(timestampMs),
  };
}

describe("metric primitives", () => {
  it("tracks counters and non-negative gauges", () => {
    const counter = new MetricCounter();
    const gauge = new MetricGauge();

    counter.increment(2);
    gauge.increment();
    gauge.decrement(3);

    expect(counter.value()).toBe(2);
    expect(gauge.value()).toBe(0);
  });

  it("calculates histogram summaries and percentiles", () => {
    const histogram = new MetricHistogram();
    [10, 20, 30, 40].forEach((value) => histogram.record(value));

    expect(histogram.snapshot()).toEqual({
      count: 4,
      min: 10,
      max: 40,
      average: 25,
      p50: 20,
      p95: 40,
      p99: 40,
    });
  });
});

describe("MetricsCollector", () => {
  it("collects counters, gauges, durations, rates, and throughput from lifecycle events", () => {
    const bus = new EventBus();
    let now = new Date(0);
    const metrics = new MetricsCollector(bus, () => now);

    bus.publish(lifecycleEvent("WorkerCreated", WorkerState.Created, 0));
    bus.publish(lifecycleEvent("WorkerValidated", WorkerState.Validated, 5));
    bus.publish(lifecycleEvent("WorkerQueued", WorkerState.Queued, 10));
    bus.publish(lifecycleEvent("WorkerDispatched", WorkerState.Dispatching, 30));
    bus.publish(lifecycleEvent("WorkerStarted", WorkerState.Running, 40));
    bus.publish(lifecycleEvent("WorkerSucceeded", WorkerState.Succeeded, 90));
    bus.publish(lifecycleEvent("WorkerCompleted", WorkerState.Completed, 100));
    now = new Date(60_000);

    const snapshot = metrics.snapshot();

    expect(snapshot.created).toBe(1);
    expect(snapshot.succeeded).toBe(1);
    expect(snapshot.failed).toBe(0);
    expect(snapshot.completed).toBe(1);
    expect(snapshot.queueDepth).toBe(0);
    expect(snapshot.activeWorkers).toBe(0);
    expect(snapshot.successRate).toBe(1);
    expect(snapshot.failureRate).toBe(0);
    expect(snapshot.throughputPerMinute).toBe(1);
    expect(snapshot.queueDurationMs.average).toBe(20);
    expect(snapshot.dispatchDurationMs.average).toBe(10);
    expect(snapshot.executionDurationMs.average).toBe(60);
    expect(Object.isFrozen(snapshot)).toBe(true);
  });

  it("tracks failures and retries without allowing gauges to become negative", () => {
    const bus = new EventBus();
    const metrics = new MetricsCollector(bus, () => new Date(60_000));

    bus.publish(lifecycleEvent("WorkerRetryPending", WorkerState.RetryPending, 10));
    bus.publish(lifecycleEvent("WorkerFailed", WorkerState.Failed, 20));
    bus.publish(lifecycleEvent("WorkerCompleted", WorkerState.Completed, 30));

    const snapshot = metrics.snapshot();
    expect(snapshot.retries).toBe(1);
    expect(snapshot.failed).toBe(1);
    expect(snapshot.failureRate).toBe(1);
    expect(snapshot.queueDepth).toBe(0);
    expect(snapshot.activeWorkers).toBe(0);
  });

  it("stops collecting after unsubscribe", () => {
    const bus = new EventBus();
    const metrics = new MetricsCollector(bus);
    metrics.stop();

    bus.publish(lifecycleEvent("WorkerCreated", WorkerState.Created, 0));

    expect(metrics.snapshot().created).toBe(0);
  });
});
