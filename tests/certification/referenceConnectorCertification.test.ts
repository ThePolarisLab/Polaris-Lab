import {
  ConnectorCapability,
  ConnectorState,
  IConnector,
  SynchronizationMode,
} from "../../src/hermes/connectors/contracts";
import { OutlookConnector } from "../../src/hermes/connectors/outlook";
import { MotiveConnector } from "../../src/hermes/connectors/motive";
import { QuickBooksConnector } from "../../src/hermes/connectors/quickbooks";

const scope = { organizationId: "org-cert", tenantId: "tenant-cert" };
const otherScope = { organizationId: "org-other", tenantId: "tenant-other" };
const credentialReference = "secret://certification/provider";

interface ConnectorCase {
  name: string;
  provider: string;
  checkpointSchema: string;
  create(): IConnector;
}

const cases: ConnectorCase[] = [
  {
    name: "Outlook",
    provider: "microsoft-outlook",
    checkpointSchema: "outlook-delta-v1",
    create: () => new OutlookConnector({
      authenticate: async () => undefined,
      listFolders: async () => [{ id: "inbox", displayName: "Inbox" }],
      listMessagesDelta: async () => ({
        messages: [{
          id: "message-1",
          subject: "Certified evidence",
          toRecipients: ["ops@example.com"],
          ccRecipients: [],
          receivedAt: "2026-07-25T12:00:00.000Z",
          hasAttachments: false,
          attachments: [],
        }],
        deltaLink: "delta-certified",
      }),
      disconnect: async () => undefined,
    }, {
      connectorId: "outlook-certification",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      credentialReference,
    }),
  },
  {
    name: "Motive",
    provider: "motive",
    checkpointSchema: "motive-checkpoint-v1",
    create: () => new MotiveConnector({
      authenticate: async () => undefined,
      list: async (resource: string) => ({
        records: [{ id: `${resource}-1`, updatedAt: "2026-07-25T12:00:00.000Z" }],
      }),
      health: async () => ({ healthy: true }),
      disconnect: async () => undefined,
    }, {
      connectorId: "motive-certification",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      credentialReference,
      resources: ["vehicle"],
    }),
  },
  {
    name: "QuickBooks",
    provider: "quickbooks-online",
    checkpointSchema: "quickbooks-checkpoint-v1",
    create: () => new QuickBooksConnector({
      authenticate: async () => undefined,
      list: async (resource: string) => ({
        records: [{ id: `${resource}-1`, updatedAt: "2026-07-25T12:00:00.000Z" }],
      }),
      report: async (report: string) => ({
        id: `${report}-current`,
        updatedAt: "2026-07-25T12:00:00.000Z",
        report,
      }),
      health: async () => ({ healthy: true }),
      disconnect: async () => undefined,
    }, {
      connectorId: "quickbooks-certification",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      credentialReference,
      resources: ["invoice"],
      reports: ["profit-and-loss"],
    }),
  },
];

function request(correlationId: string) {
  return {
    scope,
    mode: SynchronizationMode.Full,
    requestedAt: "2026-07-25T13:00:00.000Z",
    correlationId,
  };
}

describe.each(cases)("$name reference connector certification", (connectorCase) => {
  it("conforms to the provider-neutral descriptor contract", () => {
    const connector = connectorCase.create();

    expect(connector.descriptor.identity.provider).toBe(connectorCase.provider);
    expect(connector.descriptor.scope).toEqual(scope);
    expect(connector.descriptor.capabilities).toEqual(expect.arrayContaining([
      ConnectorCapability.Read,
      ConnectorCapability.FullSync,
      ConnectorCapability.IncrementalSync,
      ConnectorCapability.HealthCheck,
    ]));
    expect(connector.descriptor.supportedSyncModes).toEqual([
      SynchronizationMode.Full,
      SynchronizationMode.Incremental,
    ]);
  });

  it("fails closed when organization or tenant scope does not match", async () => {
    const connector = connectorCase.create();

    await expect(connector.connect({
      scope: otherScope,
      correlationId: "scope-negative",
      credentialReference,
    })).rejects.toThrow("scope");
    expect(connector.state).toBe(ConnectorState.Ready);
  });

  it("emits governed evidence without leaking credential references", async () => {
    const connector = connectorCase.create();
    await connector.connect({ scope, correlationId: "connect", credentialReference });

    const result = await connector.synchronize(request("sync-1"));

    expect(result.connectorId).toBe(connector.descriptor.identity.id);
    expect(result.scope).toEqual(scope);
    expect(result.failures).toEqual([]);
    expect(result.evidence.length).toBeGreaterThan(0);
    expect(result.checkpoint?.schemaVersion).toBe(connectorCase.checkpointSchema);

    for (const evidence of result.evidence) {
      expect(evidence.organizationId).toBe(scope.organizationId);
      expect(evidence.tenantId).toBe(scope.tenantId);
      expect(evidence.source.connectorId).toBe(connector.descriptor.identity.id);
      expect(evidence.source.provider).toBe(connectorCase.provider);
      expect(evidence.source.sourceRecordId).toBeTruthy();
      expect(evidence.schemaVersion).toBeTruthy();
      expect(evidence.idempotencyKey).toBeTruthy();
      expect(JSON.stringify(evidence)).not.toContain(credentialReference);
    }
  });

  it("produces deterministic idempotency keys when source data is replayed", async () => {
    const connector = connectorCase.create();
    await connector.connect({ scope, correlationId: "connect", credentialReference });

    const first = await connector.synchronize(request("replay-1"));
    const second = await connector.synchronize(request("replay-2"));

    expect(second.evidence.map((item) => item.idempotencyKey)).toEqual(
      first.evidence.map((item) => item.idempotencyKey),
    );
  });

  it("reports healthy lifecycle state and disconnects cleanly", async () => {
    const connector = connectorCase.create();
    const context = { scope, correlationId: "health", credentialReference };

    await connector.connect(context);
    const health = await connector.health(context);
    expect(health.connectorId).toBe(connector.descriptor.identity.id);
    expect(health.scope).toEqual(scope);
    expect(health.status).toBe("healthy");

    await connector.disconnect(context);
    expect(connector.state).toBe(ConnectorState.Disconnected);
  });
});
