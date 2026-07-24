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
import { GraphMailClient, OutlookFolder, OutlookMessage } from "./GraphMailClient";

export interface OutlookEvidence {
  readonly kind: "outlook-message";
  readonly message: OutlookMessage;
}

export interface OutlookConnectorOptions {
  readonly connectorId: string;
  readonly organizationId: string;
  readonly tenantId: string;
  readonly credentialReference?: string;
  readonly version?: string;
}

export class OutlookConnector extends AbstractConnector<OutlookEvidence> {
  private folders: readonly OutlookFolder[] = [];

  public constructor(
    private readonly client: GraphMailClient,
    options: OutlookConnectorOptions,
  ) {
    const descriptor: ConnectorDescriptor = {
      identity: {
        id: options.connectorId,
        provider: "microsoft-outlook",
        displayName: "Microsoft Outlook",
        version: options.version ?? "1.0.0",
      },
      scope: {
        organizationId: options.organizationId,
        tenantId: options.tenantId,
      },
      capabilities: [
        ConnectorCapability.Read,
        ConnectorCapability.FullSync,
        ConnectorCapability.IncrementalSync,
        ConnectorCapability.Attachments,
        ConnectorCapability.HealthCheck,
      ],
      supportedSyncModes: [SynchronizationMode.Full, SynchronizationMode.Incremental],
      credentialReference: options.credentialReference,
    };

    super(descriptor);
  }

  public get discoveredFolders(): readonly OutlookFolder[] {
    return this.folders;
  }

  protected async onConnect(context: ConnectorContext): Promise<void> {
    await this.client.authenticate(context.credentialReference ?? this.descriptor.credentialReference, context.signal);
    this.folders = await this.client.listFolders(context.signal);
  }

  protected async onSynchronize(
    request: SynchronizationRequest,
  ): Promise<SynchronizationResult<OutlookEvidence>> {
    const startedAt = new Date().toISOString();
    const cursor = request.mode === SynchronizationMode.Incremental
      ? request.checkpoint?.cursor
      : undefined;
    const evidence: EvidenceEnvelope<OutlookEvidence>[] = [];
    let nextCursor = cursor;
    let pageCursor = cursor;
    let remaining = request.limit;

    do {
      const page = await this.client.listMessagesDelta(pageCursor, remaining);
      for (const message of page.messages) {
        evidence.push(this.toEvidence(message, request));
      }

      if (remaining !== undefined) {
        remaining -= page.messages.length;
        if (remaining <= 0) {
          nextCursor = page.nextLink ?? page.deltaLink ?? pageCursor;
          break;
        }
      }

      pageCursor = page.nextLink;
      nextCursor = page.deltaLink ?? page.nextLink ?? nextCursor;
    } while (pageCursor);

    return {
      connectorId: this.descriptor.identity.id,
      scope: request.scope,
      startedAt,
      completedAt: new Date().toISOString(),
      mode: request.mode,
      evidence,
      failures: [],
      checkpoint: nextCursor ? {
        cursor: nextCursor,
        observedAt: new Date().toISOString(),
        schemaVersion: "outlook-delta-v1",
      } : undefined,
      partial: Boolean(pageCursor),
    };
  }

  protected async onHealth(context: ConnectorContext): Promise<ConnectorHealthReport> {
    const connected = this.state === ConnectorState.Connected || this.state === ConnectorState.Synchronizing;
    return {
      connectorId: this.descriptor.identity.id,
      scope: context.scope,
      status: connected ? ConnectorHealthStatus.Healthy : ConnectorHealthStatus.Unhealthy,
      state: this.state,
      checkedAt: new Date().toISOString(),
      details: { discoveredFolderCount: this.folders.length },
    };
  }

  protected async onDisconnect(): Promise<void> {
    await this.client.disconnect();
    this.folders = [];
  }

  private toEvidence(
    message: OutlookMessage,
    request: SynchronizationRequest,
  ): EvidenceEnvelope<OutlookEvidence> {
    const observedAt = message.receivedAt ?? message.sentAt ?? request.requestedAt;
    return {
      organizationId: request.scope.organizationId,
      tenantId: request.scope.tenantId,
      source: {
        connectorId: this.descriptor.identity.id,
        provider: this.descriptor.identity.provider,
        sourceRecordId: message.id,
        sourceReference: message.webLink,
      },
      observedAt,
      ingestedAt: new Date().toISOString(),
      correlationId: request.correlationId,
      schemaVersion: "outlook-message-v1",
      idempotencyKey: `${this.descriptor.identity.id}:${message.id}`,
      payload: { kind: "outlook-message", message },
    };
  }
}
