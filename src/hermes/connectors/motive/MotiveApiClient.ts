export type MotiveResourceType =
  | "vehicle"
  | "driver"
  | "vehicle-location"
  | "vehicle-utilization"
  | "driver-utilization"
  | "ifta-summary";

export interface MotiveRecord {
  readonly id: string;
  readonly updatedAt?: string;
  readonly [key: string]: unknown;
}

export interface MotivePage {
  readonly records: readonly MotiveRecord[];
  readonly nextCursor?: string;
  readonly observedAt?: string;
}

export interface MotiveApiClient {
  authenticate(credentialReference?: string, signal?: AbortSignal): Promise<void>;
  list(
    resource: MotiveResourceType,
    updatedAfter?: string,
    cursor?: string,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<MotivePage>;
  health(signal?: AbortSignal): Promise<{ readonly healthy: boolean; readonly message?: string }>;
  disconnect(): Promise<void>;
}
