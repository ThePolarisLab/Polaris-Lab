export enum HealthStatus {
  Healthy = "healthy",
  Degraded = "degraded",
  Unhealthy = "unhealthy",
  Critical = "critical",
}

export const HEALTH_STATUS_RANK: Readonly<Record<HealthStatus, number>> = Object.freeze({
  [HealthStatus.Healthy]: 0,
  [HealthStatus.Degraded]: 1,
  [HealthStatus.Unhealthy]: 2,
  [HealthStatus.Critical]: 3,
});
