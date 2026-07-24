import { SynchronizationMode } from "../../src/hermes/connectors/contracts";
import {
  QuickBooksApiClient,
  QuickBooksConnector,
  QuickBooksPage,
  QuickBooksRecord,
  QuickBooksReportType,
  QuickBooksResourceType,
} from "../../src/hermes/connectors/quickbooks";
import { InMemoryCheckpointStore } from "../../src/hermes/runtime/CheckpointStore";
import { ConnectorRegistry } from "../../src/hermes/runtime/ConnectorRegistry";
import { ConnectorRuntime } from "../../src/hermes/runtime/ConnectorRuntime";

class FakeQuickBooksClient implements QuickBooksApiClient {
  public authenticatedWith?: string;
  public disconnected = false;
  public readonly changedSinceValues: Array<string | undefined> = [];

  public async authenticate(credentialReference?: string): Promise<void> {
    this.authenticatedWith = credentialReference;
  }

  public async list(
    resource: QuickBooksResourceType,
    changedSince?: string,
  ): Promise<QuickBooksPage> {
    this.changedSinceValues.push(changedSince);
    return {
      records: [{
        id: `${resource}-1`,
        updatedAt: changedSince ? "2026-07-25T12:00:00.000Z" : "2026-07-24T12:00:00.000Z",
        displayName: resource === "customer" ? "Example Customer" : undefined,
      }],
    };
  }

  public async report(report: QuickBooksReportType, changedSince?: string): Promise<QuickBooksRecord> {
    return {
      id: `${report}-current`,
      updatedAt: changedSince ? "2026-07-25T12:00:00.000Z" : "2026-07-24T12:00:00.000Z",
      report,
    };
  }

  public async health(): Promise<{ healthy: boolean }> {
    return { healthy: true };
  }

  public async disconnect(): Promise<void> {
    this.disconnected = true;
  }
}

const scope = { organizationId: "org-1", tenantId: "tenant-1" };
const context = {
  scope,
  correlationId: "corr-1",
  credentialReference: "secret://quickbooks",
};

describe("QuickBooksConnector", () => {
  it("authenticates and maps financial records and reports to evidence", async () => {
    const client = new FakeQuickBooksClient();
    const connector = new QuickBooksConnector(client, {
      connectorId: "quickbooks-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      resources: ["customer", "invoice"],
      reports: ["profit-and-loss"],
    });

    await connector.connect(context);
    const result = await connector.synchronize({
      scope,
      mode: SynchronizationMode.Full,
      requestedAt: "2026-07-24T13:00:00.000Z",
      correlationId: "corr-1",
    });

    expect(client.authenticatedWith).toBe("secret://quickbooks");
    expect(result.evidence).toHaveLength(3);
    expect(result.evidence[0].payload.resource).toBe("customer");
    expect(result.evidence[2].payload.kind).toBe("quickbooks-report");
    expect(result.checkpoint?.schemaVersion).toBe("quickbooks-checkpoint-v1");
  });

  it("reuses the latest timestamp through the Hermes runtime checkpoint", async () => {
    const client = new FakeQuickBooksClient();
    const connector = new QuickBooksConnector(client, {
      connectorId: "quickbooks-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      credentialReference: "secret://quickbooks",
      resources: ["invoice"],
      reports: [],
    });
    const registry = new ConnectorRegistry();
    registry.register(connector);
    const runtime = new ConnectorRuntime(
      registry,
      new InMemoryCheckpointStore(),
      { maxAttempts: 1, delayMs: 0 },
    );

    await runtime.synchronize("quickbooks-primary", context, SynchronizationMode.Incremental, "corr-1");
    await runtime.synchronize("quickbooks-primary", context, SynchronizationMode.Incremental, "corr-2");

    expect(client.changedSinceValues).toEqual([undefined, "2026-07-24T12:00:00.000Z"]);
  });

  it("reports health and disconnects cleanly", async () => {
    const client = new FakeQuickBooksClient();
    const connector = new QuickBooksConnector(client, {
      connectorId: "quickbooks-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      resources: ["account"],
      reports: ["balance-sheet"],
    });

    await connector.connect(context);
    const health = await connector.health(context);
    await connector.disconnect(context);

    expect(health.status).toBe("healthy");
    expect(client.disconnected).toBe(true);
  });
});
