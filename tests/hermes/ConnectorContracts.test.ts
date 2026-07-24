import {
  AbstractConnector,
  ConnectorCapability,
  ConnectorContext,
  ConnectorContractError,
  ConnectorDescriptor,
  ConnectorHealthStatus,
  ConnectorState,
  EvidenceEnvelope,
  SynchronizationMode,
  SynchronizationRequest,
  SynchronizationResult,
  validateDescriptor,
  validateEvidenceEnvelope,
} from "../../src/hermes/connectors";

interface RecordPayload {
  readonly subject: string;
}

const scope = Object.freeze({ organizationId: "org-mor", tenantId: "tenant-ca" });

const descriptor: ConnectorDescriptor = Object.freeze({
  identity: Object.freeze({
    id: "reference.connector",
    provider: "reference",
    displayName: "Reference Connector",
    version: "1.0.0",
  }),
  scope,
  capabilities: Object.freeze([
    ConnectorCapability.Read,
    ConnectorCapability.IncrementalSync,
    ConnectorCapability.HealthCheck,
  ]),
  supportedSyncModes: Object.freeze([SynchronizationMode.Incremental]),
  credentialReference: "secret://reference/oauth",
});

const context: ConnectorContext = Object.freeze({
  scope,
  correlationId: "correlation-1",
  credentialReference: descriptor.credentialReference,
});

const request: SynchronizationRequest = Object.freeze({
  scope,
  mode: SynchronizationMode.Incremental,
  requestedAt: "2026-07-24T12:00:00.000Z",
  correlationId: "correlation-1",
});

const evidence: EvidenceEnvelope<RecordPayload> = Object.freeze({
  organizationId: scope.organizationId,
  tenantId: scope.tenantId,
  source: Object.freeze({
    connectorId: descriptor.identity.id,
    provider: descriptor.identity.provider,
    sourceRecordId: "message-1",
    sourceReference: "provider://message-1",
  }),
  observedAt: "2026-07-24T11:59:00.000Z",
  ingestedAt: "2026-07-24T12:00:01.000Z",
  correlationId: "correlation-1",
  schemaVersion: "1.0.0",
  idempotencyKey: "reference.connector:message-1:v1",
  payload: Object.freeze({ subject: "Load opportunity" }),
});

class ReferenceConnector extends AbstractConnector<RecordPayload> {
  public connectCalls = 0;
  public disconnectCalls = 0;

  public constructor() {
    super(descriptor);
  }

  protected async onConnect(): Promise<void> {
    this.connectCalls += 1;
  }

  protected async onSynchronize(
    synchronizationRequest: SynchronizationRequest,
  ): Promise<SynchronizationResult<RecordPayload>> {
    return Object.freeze({
      connectorId: this.descriptor.identity.id,
      scope: synchronizationRequest.scope,
      startedAt: "2026-07-24T12:00:00.000Z",
      completedAt: "2026-07-24T12:00:02.000Z",
      mode: synchronizationRequest.mode,
      evidence: Object.freeze([evidence]),
      failures: Object.freeze([]),
      partial: false,
      checkpoint: Object.freeze({
        cursor: "cursor-2",
        observedAt: "2026-07-24T12:00:02.000Z",
        schemaVersion: "1.0.0",
      }),
    });
  }

  protected async onDisconnect(): Promise<void> {
    this.disconnectCalls += 1;
  }
}

describe("Hermes connector contracts", () => {
  it("requires identity, scope, capabilities, and synchronization modes", () => {
    expect(() => validateDescriptor(descriptor)).not.toThrow();

    expect(() => validateDescriptor({ ...descriptor, capabilities: [] })).toThrow(
      ConnectorContractError,
    );
  });

  it("requires tenant, provenance, schema, and idempotency evidence", () => {
    expect(() => validateEvidenceEnvelope(evidence)).not.toThrow();

    expect(() =>
      validateEvidenceEnvelope({ ...evidence, idempotencyKey: "" }),
    ).toThrow("idempotencyKey is required");
  });

  it("enforces the connector lifecycle and exposes health", async () => {
    const connector = new ReferenceConnector();

    expect(connector.state).toBe(ConnectorState.Ready);
    await expect(connector.synchronize(request)).rejects.toMatchObject({
      code: "HERMES_INVALID_CONNECTOR_STATE",
    });

    await connector.connect(context);
    expect(connector.state).toBe(ConnectorState.Connected);
    expect(connector.connectCalls).toBe(1);

    const result = await connector.synchronize(request);
    expect(result.evidence).toEqual([evidence]);
    expect(result.checkpoint?.cursor).toBe("cursor-2");
    expect(connector.state).toBe(ConnectorState.Connected);

    const health = await connector.health(context);
    expect(health.status).toBe(ConnectorHealthStatus.Healthy);
    expect(health.connectorId).toBe(descriptor.identity.id);

    await connector.disconnect(context);
    expect(connector.state).toBe(ConnectorState.Disconnected);
    expect(connector.disconnectCalls).toBe(1);
  });

  it("rejects cross-tenant requests", async () => {
    const connector = new ReferenceConnector();

    await expect(
      connector.connect({
        ...context,
        scope: { organizationId: "org-mor", tenantId: "tenant-us" },
      }),
    ).rejects.toMatchObject({ code: "HERMES_SCOPE_MISMATCH" });
  });
});
