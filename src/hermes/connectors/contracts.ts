export type ConnectorId = string;
export type TenantId = string;
export type OrganizationId = string;
export type SchemaVersion = string;
export type CredentialReference = string;

export enum ConnectorCapability {
  Read = "read",
  Write = "write",
  IncrementalSync = "incremental-sync",
  FullSync = "full-sync",
  Webhook = "webhook",
  Attachments = "attachments",
  HealthCheck = "health-check",
}

export enum ConnectorState {
  Unconfigured = "unconfigured",
  Ready = "ready",
  Authenticating = "authenticating",
  Connected = "connected",
  Synchronizing = "synchronizing",
  Degraded = "degraded",
  Failed = "failed",
  Disconnected = "disconnected",
}

export enum ConnectorHealthStatus {
  Unknown = "unknown",
  Healthy = "healthy",
  Degraded = "degraded",
  Unhealthy = "unhealthy",
}

export enum SynchronizationMode {
  Full = "full",
  Incremental = "incremental",
}

export interface ConnectorIdentity {
  readonly id: ConnectorId;
  readonly provider: string;
  readonly displayName: string;
  readonly version: string;
}

export interface ConnectorScope {
  readonly organizationId: OrganizationId;
  readonly tenantId: TenantId;
}

export interface ConnectorDescriptor {
  readonly identity: ConnectorIdentity;
  readonly scope: ConnectorScope;
  readonly capabilities: readonly ConnectorCapability[];
  readonly supportedSyncModes: readonly SynchronizationMode[];
  readonly credentialReference?: CredentialReference;
}

export interface ConnectorCheckpoint {
  readonly cursor: string;
  readonly observedAt: string;
  readonly schemaVersion: SchemaVersion;
}

export interface SynchronizationRequest {
  readonly scope: ConnectorScope;
  readonly mode: SynchronizationMode;
  readonly requestedAt: string;
  readonly correlationId: string;
  readonly checkpoint?: ConnectorCheckpoint;
  readonly limit?: number;
}

export interface EvidenceSource {
  readonly connectorId: ConnectorId;
  readonly provider: string;
  readonly sourceRecordId: string;
  readonly sourceReference?: string;
}

export interface EvidenceEnvelope<TPayload = unknown> {
  readonly organizationId: OrganizationId;
  readonly tenantId: TenantId;
  readonly source: EvidenceSource;
  readonly observedAt: string;
  readonly ingestedAt: string;
  readonly correlationId: string;
  readonly causationId?: string;
  readonly schemaVersion: SchemaVersion;
  readonly idempotencyKey: string;
  readonly payload: Readonly<TPayload>;
  readonly integrity?: Readonly<Record<string, string>>;
  readonly extensions?: Readonly<Record<string, unknown>>;
}

export interface SynchronizationFailure {
  readonly code: string;
  readonly message: string;
  readonly retryable: boolean;
  readonly sourceRecordId?: string;
}

export interface SynchronizationResult<TPayload = unknown> {
  readonly connectorId: ConnectorId;
  readonly scope: ConnectorScope;
  readonly startedAt: string;
  readonly completedAt: string;
  readonly mode: SynchronizationMode;
  readonly evidence: readonly EvidenceEnvelope<TPayload>[];
  readonly failures: readonly SynchronizationFailure[];
  readonly checkpoint?: ConnectorCheckpoint;
  readonly partial: boolean;
}

export interface ConnectorHealthReport {
  readonly connectorId: ConnectorId;
  readonly scope: ConnectorScope;
  readonly status: ConnectorHealthStatus;
  readonly state: ConnectorState;
  readonly checkedAt: string;
  readonly message?: string;
  readonly retryAfterMs?: number;
  readonly details?: Readonly<Record<string, unknown>>;
}

export interface ConnectorContext {
  readonly scope: ConnectorScope;
  readonly correlationId: string;
  readonly credentialReference?: CredentialReference;
  readonly signal?: AbortSignal;
}

export interface IConnector<TPayload = unknown> {
  readonly descriptor: ConnectorDescriptor;
  readonly state: ConnectorState;

  connect(context: ConnectorContext): Promise<void>;
  synchronize(request: SynchronizationRequest): Promise<SynchronizationResult<TPayload>>;
  health(context: ConnectorContext): Promise<ConnectorHealthReport>;
  disconnect(context: ConnectorContext): Promise<void>;
}
