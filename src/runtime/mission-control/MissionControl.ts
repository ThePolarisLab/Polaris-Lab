import { IHealthProvider } from "../health/IHealthProvider";
import { IMetricsProvider } from "../metrics/IMetricsProvider";
import { IScheduler } from "../scheduler/IScheduler";
import { WorkerRegistry } from "../sdk/WorkerRegistry";
import { IMissionControl } from "./IMissionControl";
import { MissionControlSnapshot } from "./MissionControlSnapshot";

export class MissionControl implements IMissionControl {
  constructor(
    private readonly registry: WorkerRegistry,
    private readonly scheduler: IScheduler,
    private readonly metrics: IMetricsProvider,
    private readonly health: IHealthProvider,
    private readonly runtimeVersion = "0.1.0-alpha",
    private readonly clock: () => Date = () => new Date(),
  ) {}

  snapshot(): MissionControlSnapshot {
    const health = this.health.snapshot();
    const metrics = this.metrics.snapshot();
    const workers = Object.freeze(
      this.registry.list().map((worker) => Object.freeze({
        name: worker.definition.name,
        version: worker.definition.version,
        ...(worker.definition.description
          ? { description: worker.definition.description }
          : {}),
      })),
    );

    return Object.freeze({
      timestamp: new Date(this.clock()),
      runtimeVersion: this.runtimeVersion,
      health: health.status,
      alerts: Object.freeze([...health.alerts]),
      workers,
      queueDepth: this.scheduler.size,
      metrics,
    });
  }
}
