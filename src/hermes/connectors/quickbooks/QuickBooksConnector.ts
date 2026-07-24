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
import {
  QuickBooksApiClient,
  QuickBooksRecord,
  QuickBooksReportType,
  QuickBooksResourceType,
} from "./QuickBooksApiClient";

export interface QuickBooksEvidence {
  readonly kind: "quickbooks-record" | "quickbooks-report";
  readonly resource: QuickBooksResourceType | QuickBooksReportType;
  readonly record: QuickBooksRecord;
}

export interface QuickBooksConnectorOptions {
  readonly connectorId: string;
  readonly organizationId: string;
  readonly tenantId: string;
  readonly credentialReference?: string;
  readonly version?: string;
  readonly resources?: readonly QuickBooksResourceType[];
  readonly reports?: readonly QuickBooksReportType[];
}

const DEFAULT_RESOURCES: readonly QuickBooksResourceType[] = [
  "company", "customer", "vendor", "account", "invoice", "payment", "bill", "purchase", "journal-entry",
];

const DEFAULT_REPORTS: readonly QuickBooksReportType[] = [
  "profit-and-loss", "balance-sheet", "cash-flow", "aged-receivables", "aged-payables",
];

interface QuickBooksCheckpointState {
  readonly changedSince?: string;
  readonly cursors?: Readonly<Partial<Record<QuickBooksResourceType, string>>>;
}

export class QuickBooksConnector extends AbstractConnector<QuickBooksEvidence> {
  private readonly resources: readonly QuickBooksResourceType[];
  private readonly reports: readonly QuickBooksReportType[];

  public constructor(
    private readonly client: QuickBooksApiClient,
    options: QuickBooksConnectorOptions,
  ) {
    const descriptor: ConnectorDescriptor = {
      identity: {
        id: options.connectorId,
        provider: "quickbooks",
        displayName: "QuickBooks Online",
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
    this.reports = options.reports ?? DEFAULT_REPORTS;
  }

  protected async onConnect(context: ConnectorContext): Promise<void> {
    await this.client.authenticate(
      context.credentialReference ?? this.descriptor.credentialReference,
      context.signal,
    );
  }

  protected async onSynchronize(
    request: SynchronizationRequest,
  ): Promise<SynchronizationResult<QuickBooksEvidence>> {
    const startedAt = new Date().toISOString();
    const state = request.mode === SynchronizationMode.Incremental
      ? this.parseCheckpoint(request.checkpoint?.cursor)
      : {};
    const evidence: EvidenceEnvelope<QuickBooksEvidence>[] = [];
    const cursors: Partial<Record<QuickBooksResourceType, string>> = {};
    let partial = false;
    let latestObservedAt = state.changedSince;

    for (const resource of this.resources) {
      let cursor = state.cursors?.[resource];
      do {
        const page = await this.client.list(
          resource,
          state.changedSince,
          cursor,
          request.limit,
          request.signal,
        );
        for (const record of page.records) {
          evidence.push(this.toEvidence("quickbooks-record", resource, record, request));
          if (record.updatedAt && (!latestObservedAt || record.updatedAt > latestObservedAt)) {
            latestObservedAt = record.updatedAt;
          }
        }
        cursor = page.nextCursor;
        if (cursor) cursors[resource] = cursor;
      } while (cursor && request.limit === undefined);

      if (cursor) partial = true;
    }

    for (const report of this.reports) {
      const record = await this.client.report(report, state.changedSince, request.signal);
      evidence.push(this.toEvidence("quickbooks-report", report, record, request));
      if (record.updatedAt && (!latestObservedAt || record.updatedAt > latestObservedAt)) {
        latestObservedAt = record.updatedAt;
      }
    }

    const checkpointState: QuickBooksCheckpointState = {
      changedSince: latestObservedAt ?? request.requestedAt,
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
        schemaVersion: "quickbooks-checkpoint-v1",
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
      details: { resources: this.resources, reports: this.reports },
    };
  }

  protected async onDisconnect(): Promise<void> {
    await this.client.disconnect();
  }

  private parseCheckpoint(cursor?: string): QuickBooksCheckpointState {
    if (!cursor) return {};
    try {
      return JSON.parse(cursor) as QuickBooksCheckpointState;
    } catch {
      return { changedSince: cursor };
    }
  }

  private toEvidence(
    kind: QuickBooksEvidence["kind"],
    resource: QuickBooksResourceType | QuickBooksReportType,
    record: QuickBooksRecord,
    request: SynchronizationRequest,
  ): EvidenceEnvelope<QuickBooksEvidence> {
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
      schemaVersion: "quickbooks-evidence-v1",
      idempotencyKey: `${this.descriptor.identity.id}:${resource}:${record.id}:${record.updatedAt ?? "current"}`,
      payload: { kind, resource, record },
    };
  }
}
