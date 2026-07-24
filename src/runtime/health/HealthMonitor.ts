import { IMetricsProvider } from "../metrics/IMetricsProvider";
import { MetricsSnapshot } from "../metrics/MetricsSnapshot";
import { HealthAlert, HealthCategory } from "./HealthAlert";
import { HealthSnapshot } from "./HealthSnapshot";
import { HEALTH_STATUS_RANK, HealthStatus } from "./HealthStatus";
import { DEFAULT_HEALTH_THRESHOLDS, HealthThresholds } from "./HealthThresholds";
import { IHealthProvider } from "./IHealthProvider";

type Severity = Exclude<HealthStatus, HealthStatus.Healthy>;

export class HealthMonitor implements IHealthProvider {
  constructor(
    private readonly metrics: IMetricsProvider,
    private readonly thresholds: HealthThresholds = DEFAULT_HEALTH_THRESHOLDS,
  ) {}

  status(): HealthStatus {
    return this.snapshot().status;
  }

  alerts(): readonly HealthAlert[] {
    return this.snapshot().alerts;
  }

  isHealthy(): boolean {
    return this.status() === HealthStatus.Healthy;
  }

  isCritical(): boolean {
    return this.status() === HealthStatus.Critical;
  }

  snapshot(): HealthSnapshot {
    const metrics = this.metrics.snapshot();
    const alerts = Object.freeze(this.evaluate(metrics));
    const status = alerts.reduce<HealthStatus>(
      (current, alert) => HEALTH_STATUS_RANK[alert.severity] > HEALTH_STATUS_RANK[current] ? alert.severity : current,
      HealthStatus.Healthy,
    );

    return Object.freeze({
      timestamp: new Date(metrics.timestamp),
      status,
      alerts,
    });
  }

  private evaluate(metrics: MetricsSnapshot): HealthAlert[] {
    const alerts: HealthAlert[] = [];
    this.addHigh(alerts, "failures", metrics.failureRate, this.thresholds.failureRate,
      "Worker failure rate exceeded its health threshold.", "Inspect failed executions and worker dependencies.");
    this.addHigh(alerts, "queue", metrics.queueDepth, this.thresholds.queueDepth,
      "Runtime queue depth exceeded its health threshold.", "Increase worker capacity or inspect blocked dispatches.");

    const retryRate = metrics.created === 0 ? 0 : metrics.retries / metrics.created;
    this.addHigh(alerts, "retries", retryRate, this.thresholds.retryRate,
      "Runtime retry rate indicates a retry storm.", "Inspect transient failures and retry policies.");

    const timeoutRate = metrics.started === 0 ? 0 : metrics.timedOut / metrics.started;
    this.addHigh(alerts, "timeouts", timeoutRate, this.thresholds.timeoutRate,
      "Worker timeout rate exceeded its health threshold.", "Inspect long-running workers and timeout configuration.");

    this.addHigh(alerts, "latency", metrics.executionDurationMs.p95, this.thresholds.executionP95Ms,
      "P95 execution latency exceeded its health threshold.", "Profile slow workers and downstream dependencies.");

    if (metrics.completed > 0) {
      this.addLow(alerts, "throughput", metrics.throughputPerMinute, this.thresholds.minimumThroughputPerMinute,
        "Runtime throughput fell below its health threshold.", "Inspect queue flow, worker capacity, and downstream bottlenecks.");
    }
    return alerts;
  }

  private addHigh(alerts: HealthAlert[], category: HealthCategory, value: number,
    thresholds: readonly [number, number, number], message: string, suggestedAction: string): void {
    const severity = this.highSeverity(value, thresholds);
    if (severity) alerts.push(this.alert(category, severity, value, this.thresholdFor(severity, thresholds), message, suggestedAction));
  }

  private addLow(alerts: HealthAlert[], category: HealthCategory, value: number,
    thresholds: readonly [number, number, number], message: string, suggestedAction: string): void {
    const severity = value < thresholds[2] ? HealthStatus.Critical
      : value < thresholds[1] ? HealthStatus.Unhealthy
      : value < thresholds[0] ? HealthStatus.Degraded : undefined;
    if (severity) alerts.push(this.alert(category, severity, value, this.thresholdFor(severity, thresholds), message, suggestedAction));
  }

  private highSeverity(value: number, thresholds: readonly [number, number, number]): Severity | undefined {
    if (value >= thresholds[2]) return HealthStatus.Critical;
    if (value >= thresholds[1]) return HealthStatus.Unhealthy;
    if (value >= thresholds[0]) return HealthStatus.Degraded;
    return undefined;
  }

  private thresholdFor(severity: Severity, thresholds: readonly [number, number, number]): number {
    return thresholds[severity === HealthStatus.Degraded ? 0 : severity === HealthStatus.Unhealthy ? 1 : 2];
  }

  private alert(category: HealthCategory, severity: Severity, observedValue: number, threshold: number,
    message: string, suggestedAction: string): HealthAlert {
    return Object.freeze({ id: `${category}.${severity}`, category, severity, message, observedValue, threshold, suggestedAction });
  }
}
