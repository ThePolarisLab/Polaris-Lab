import { AbstractConnector } from "../AbstractConnector";
import {
  ConnectorCapability,
  ConnectorContext,
  ConnectorDescriptor,
  ConnectorHealthReport,
  ConnectorHealthStatus,
  ConnectorState,
  EvidenceEnvelope,
  SynchronizationMode,
  SynchronizationRequest,
  SynchronizationResult,
} from "../contracts";
import { MotiveApiClient, MotiveRecord, MotiveResourceType } from "./MotiveApiClient";

export interface MotiveEvidence {
  readonly kind: "motive-record";
  readonly resource: MotiveResourceType;
  readonly record: MotiveRecord;
}

export interface MotiveConnectorOptions {
  readonly connectorId: string;
  readonly organizationId: string;
  readonly tenantId: string;
  readonly credentialReference?: string;
  readonly version?: string;
  readonly resources?: readonly MotiveResourceType[];
}

const DEFAULT_RESOURCES: readonly MotiveResourceType[] = [
  "vehicle",
  "driver",
  "vehicle-location",
  "vehicle-utilization",
  "driver-utilization",
  "ifta-summary",
];

interface MotiveCheckpointState {
  readonly updatedAfter?: string;
  readonly cursors?: Readonly<Partial<Record<MotiveResourceType, string>>>;
}

export class MotiveConnector extends AbstractConnector<MotiveEvidence> {
  private readonly resources: readonly MotiveResourceType[];

  public constructor(
    private readonly client: MotiveApiClient,
    options: MotiveConnectorOptions,
  ) {
    const descriptor: ConnectorDescriptor = {
      identity: {
        id: options.connectorId,
        provider: "motive",
        displayName: "Motive Fleet Management",
        version: options.version ?? "1.0.0",
      },
      scope: { organizationId: options.organizationId, tenantId: options.tenantId },
      capabilities: [
        ConnectorCapability.Read,
        ConnectorCapability.FullSync,
        ConnectorCapability.IncrementalSync,
        ConnectorCapability.HealthCheck,
      ],
      supportedSyncModes: [SynchronizationMode.Full, SynchronizationMode.Incremental],
      credentialReference: options.credentialReference,
    };

    super(descriptor);
    this.resources = options.resources ?? DEFAULT_RESOURCES;
  }

  protected async onConnect(context: ConnectorContext): Promise<void> {
    await this.client.authenticate(
      context.credentialReference ?? this.descriptor.credentialReference,
      context.signal,
    );
  }

  protected async onSynchronize(
    request: SynchronizationRequest,
  ): Promise<SynchronizationResult<MotiveEvidence>> {
    const startedAt = new Date().toISOString();
    const state = request.mode === SynchronizationMode.Incremental
      ? this.parseCheckpoint(request.checkpoint?.cursor)
      : {};
    const evidence: EvidenceEnvelope<MotiveEvidence>[] = [];
    const cursors: Partial<Record<MotiveResourceType, string>> = {};
    let partial = false;
    let latestObservedAt = state.updatedAfter;

    for (const resource of this.resources) {
      let cursor = state.cursors?.[resource];
      do {
        const page = await this.client.list(
          resource,
          state.updatedAfter,
          cursor,
          request.limit,
          undefined,
        );

        for (const record of page.records) {
          evidence.push(this.toEvidence(resource, record, request));
          if (record.updatedAt && (!latestObservedAt || record.updatedAt > latestObservedAt)) {
            latestObservedAt = record.updatedAt;
          }
        }

        cursor = page.nextCursor;
        if (cursor) cursors[resource] = cursor;
      } while (cursor && request.limit === undefined);

      if (cursor) partial = true;
    }

    const checkpointState: MotiveCheckpointState = {
      updatedAfter: latestObservedAt ?? request.requestedAt,
      cursors: partial ? cursors : undefined,
    };

    return {
      connectorId: this.descriptor.identity.id,
      scope: request.scope,
      startedAt,
      completedAt: new Date().toISOString(),
      mode: request.mode,
      evidence,
      failures: [],
      checkpoint: {
        cursor: JSON.stringify(checkpointState),
        observedAt: new Date().toISOString(),
        schemaVersion: "motive-checkpoint-v1",
      },
      partial,
    };
  }

  protected async onHealth(context: ConnectorContext): Promise<ConnectorHealthReport> {
    const result = await this.client.health(context.signal);
    return {
      connectorId: this.descriptor.identity.id,
      scope: context.scope,
      status: result.healthy ? ConnectorHealthStatus.Healthy : ConnectorHealthStatus.Unhealthy,
      state: result.healthy ? this.state : ConnectorState.Degraded,
      checkedAt: new Date().toISOString(),
      message: result.message,
      details: { resources: this.resources },
    };
  }

  protected async onDisconnect(): Promise<void> {
    await this.client.disconnect();
  }

  private parseCheckpoint(cursor?: string): MotiveCheckpointState {
    if (!cursor) return {};
    try {
      return JSON.parse(cursor) as MotiveCheckpointState;
    } catch {
      return { updatedAfter: cursor };
    }
  }

  private toEvidence(
    resource: MotiveResourceType,
    record: MotiveRecord,
    request: SynchronizationRequest,
  ): EvidenceEnvelope<MotiveEvidence> {
    return {
      organizationId: request.scope.organizationId,
      tenantId: request.scope.tenantId,
      source: {
        connectorId: this.descriptor.identity.id,
        provider: this.descriptor.identity.provider,
        sourceRecordId: `${resource}:${record.id}`,
      },
      observedAt: record.updatedAt ?? request.requestedAt,
      ingestedAt: new Date().toISOString(),
      correlationId: request.correlationId,
      schemaVersion: "motive-record-v1",
      idempotencyKey: `${this.descriptor.identity.id}:${resource}:${record.id}:${record.updatedAt ?? "current"}`,
      payload: { kind: "motive-record", resource, record },
    };
  }
}
