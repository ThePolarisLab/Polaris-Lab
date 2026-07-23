import { MetricsSnapshot } from "./MetricsSnapshot";

export interface IMetricsProvider {
  snapshot(): MetricsSnapshot;
}
