import { EventSubscription } from "../events/IEvent";
import { IEventBus } from "../events/IEventBus";
import { RuntimeLifecycleEvent } from "../lifecycle/RuntimeEvents";
import { IMetricsProvider } from "./IMetricsProvider";
import { MetricCounter } from "./MetricCounter";
import { MetricGauge } from "./MetricGauge";
import { MetricHistogram } from "./MetricHistogram";
import { MetricsSnapshot } from "./MetricsSnapshot";

type Clock = () => Date;

export class MetricsCollector implements IMetricsProvider {
  private readonly counters = {
    created: new MetricCounter(),
    validated: new MetricCounter(),
    queued: new MetricCounter(),
    dispatched: new MetricCounter(),
    started: new MetricCounter(),
    succeeded: new MetricCounter(),
    failed: new MetricCounter(),
    cancelled: new MetricCounter(),
    retries: new MetricCounter(),
    timedOut: new MetricCounter(),
    completed: new MetricCounter(),
  };

  private readonly queueDepth = new MetricGauge();
  private readonly activeWorkers = new MetricGauge();
  private readonly queueDuration = new MetricHistogram();
  private readonly dispatchDuration = new MetricHistogram();
  private readonly executionDuration = new MetricHistogram();
  private readonly queuedAt = new Map<string, number>();
  private readonly dispatchedAt = new Map<string, number>();
  private readonly startedAt = new Map<string, number>();
  private readonly startedCollectingAt: number;
  private readonly unsubscribe: EventSubscription;

  constructor(
    eventBus: IEventBus,
    private readonly clock: Clock = () => new Date(),
  ) {
    this.startedCollectingAt = this.clock().getTime();
    this.unsubscribe = eventBus.subscribeAll((event) => {
      if (this.isLifecycleEvent(event)) {
        this.record(event);
      }
    });
  }

  stop(): void {
    this.unsubscribe();
  }

  snapshot(): MetricsSnapshot {
    const now = this.clock();
    const terminal = this.counters.succeeded.value() + this.counters.failed.value();
    const elapsedMinutes = Math.max((now.getTime() - this.startedCollectingAt) / 60_000, 1 / 60_000);

    return Object.freeze({
      timestamp: new Date(now),
      created: this.counters.created.value(),
      validated: this.counters.validated.value(),
      queued: this.counters.queued.value(),
      dispatched: this.counters.dispatched.value(),
      started: this.counters.started.value(),
      succeeded: this.counters.succeeded.value(),
      failed: this.counters.failed.value(),
      cancelled: this.counters.cancelled.value(),
      retries: this.counters.retries.value(),
      timedOut: this.counters.timedOut.value(),
      completed: this.counters.completed.value(),
      queueDepth: this.queueDepth.value(),
      activeWorkers: this.activeWorkers.value(),
      successRate: terminal === 0 ? 0 : this.counters.succeeded.value() / terminal,
      failureRate: terminal === 0 ? 0 : this.counters.failed.value() / terminal,
      throughputPerMinute: this.counters.completed.value() / elapsedMinutes,
      queueDurationMs: this.queueDuration.snapshot(),
      dispatchDurationMs: this.dispatchDuration.snapshot(),
      executionDurationMs: this.executionDuration.snapshot(),
    });
  }

  private record(event: RuntimeLifecycleEvent): void {
    const timestamp = event.timestamp.getTime();

    switch (event.name) {
      case "WorkerCreated":
        this.counters.created.increment();
        break;
      case "WorkerValidated":
        this.counters.validated.increment();
        break;
      case "WorkerQueued":
        this.counters.queued.increment();
        this.queueDepth.increment();
        this.queuedAt.set(event.executionId, timestamp);
        break;
      case "WorkerDispatched":
        this.counters.dispatched.increment();
        this.queueDepth.decrement();
        this.recordElapsed(this.queueDuration, this.queuedAt, event.executionId, timestamp);
        this.dispatchedAt.set(event.executionId, timestamp);
        break;
      case "WorkerStarted":
        this.counters.started.increment();
        this.activeWorkers.increment();
        this.recordElapsed(this.dispatchDuration, this.dispatchedAt, event.executionId, timestamp);
        this.startedAt.set(event.executionId, timestamp);
        break;
      case "WorkerSucceeded":
        this.counters.succeeded.increment();
        break;
      case "WorkerFailed":
        this.counters.failed.increment();
        break;
      case "WorkerCancelled":
        this.counters.cancelled.increment();
        break;
      case "WorkerRetryPending":
        this.counters.retries.increment();
        break;
      case "WorkerTimedOut":
        this.counters.timedOut.increment();
        break;
      case "WorkerCompleted":
        this.counters.completed.increment();
        this.activeWorkers.decrement();
        this.recordElapsed(this.executionDuration, this.startedAt, event.executionId, timestamp);
        this.clearExecution(event.executionId);
        break;
    }
  }

  private recordElapsed(
    histogram: MetricHistogram,
    starts: Map<string, number>,
    executionId: string,
    end: number,
  ): void {
    const start = starts.get(executionId);
    if (start !== undefined) {
      histogram.record(Math.max(0, end - start));
      starts.delete(executionId);
    }
  }

  private clearExecution(executionId: string): void {
    this.queuedAt.delete(executionId);
    this.dispatchedAt.delete(executionId);
    this.startedAt.delete(executionId);
  }

  private isLifecycleEvent(event: { readonly name: string }): event is RuntimeLifecycleEvent {
    return event.name.startsWith("Worker");
  }
}
