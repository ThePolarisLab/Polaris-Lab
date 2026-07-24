import { HealthAlert } from "./HealthAlert";
import { HealthSnapshot } from "./HealthSnapshot";
import { HealthStatus } from "./HealthStatus";

export interface IHealthProvider {
  status(): HealthStatus;
  snapshot(): HealthSnapshot;
  alerts(): readonly HealthAlert[];
  isHealthy(): boolean;
  isCritical(): boolean;
}
