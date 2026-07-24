import { HealthAlert } from "./HealthAlert";
import { HealthStatus } from "./HealthStatus";

export interface HealthSnapshot {
  readonly timestamp: Date;
  readonly status: HealthStatus;
  readonly alerts: readonly HealthAlert[];
}
