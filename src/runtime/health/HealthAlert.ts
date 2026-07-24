import { HealthStatus } from "./HealthStatus";

export type HealthCategory = "failures" | "queue" | "retries" | "timeouts" | "latency" | "throughput";

export interface HealthAlert {
  readonly id: string;
  readonly category: HealthCategory;
  readonly severity: Exclude<HealthStatus, HealthStatus.Healthy>;
  readonly message: string;
  readonly observedValue: number;
  readonly threshold: number;
  readonly suggestedAction: string;
}
