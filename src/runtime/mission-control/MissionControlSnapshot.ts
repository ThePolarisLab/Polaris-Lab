import { HealthAlert } from "../health/HealthAlert";
import { HealthStatus } from "../health/HealthStatus";
import { MetricsSnapshot } from "../metrics/MetricsSnapshot";

export interface MissionControlWorkerSummary {
  readonly name: string;
  readonly version: string;
  readonly description?: string;
}

export interface MissionControlSnapshot {
  readonly timestamp: Date;
  readonly runtimeVersion: string;
  readonly health: HealthStatus;
  readonly alerts: readonly HealthAlert[];
  readonly workers: readonly MissionControlWorkerSummary[];
  readonly queueDepth: number;
  readonly metrics: MetricsSnapshot;
}
