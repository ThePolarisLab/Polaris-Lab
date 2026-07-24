import { SynchronizationMode } from "../../src/hermes/connectors/contracts";
import {
  MotiveApiClient,
  MotiveConnector,
  MotivePage,
  MotiveResourceType,
} from "../../src/hermes/connectors/motive";
import { InMemoryCheckpointStore } from "../../src/hermes/runtime/CheckpointStore";
import { ConnectorRegistry } from "../../src/hermes/runtime/ConnectorRegistry";
import { ConnectorRuntime } from "../../src/hermes/runtime/ConnectorRuntime";

class FakeMotiveClient implements MotiveApiClient {
  public authenticatedWith?: string;
  public disconnected = false;
  public readonly updatedAfterValues: Array<string | undefined> = [];

  public async authenticate(credentialReference?: string): Promise<void> {
    this.authenticatedWith = credentialReference;
  }

  public async list(resource: MotiveResourceType, updatedAfter?: string): Promise<MotivePage> {
    this.updatedAfterValues.push(updatedAfter);
    return {
      records: [{
        id: `${resource}-1`,
        updatedAt: updatedAfter ? "2026-07-25T12:00:00.000Z" : "2026-07-24T12:00:00.000Z",
        unitNumber: resource === "vehicle" ? "101" : undefined,
      }],
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
  credentialReference: "secret://motive",
};

describe("MotiveConnector", () => {
  it("authenticates and maps fleet records to evidence", async () => {
    const client = new FakeMotiveClient();
    const connector = new MotiveConnector(client, {
      connectorId: "motive-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      resources: ["vehicle", "driver"],
    });

    await connector.connect(context);
    const result = await connector.synchronize({
      scope,
      mode: SynchronizationMode.Full,
      requestedAt: "2026-07-24T13:00:00.000Z",
      correlationId: "corr-1",
    });

    expect(client.authenticatedWith).toBe("secret://motive");
    expect(result.evidence).toHaveLength(2);
    expect(result.evidence[0].payload.resource).toBe("vehicle");
    expect(result.evidence[0].source.sourceRecordId).toBe("vehicle:vehicle-1");
    expect(result.checkpoint?.schemaVersion).toBe("motive-checkpoint-v1");
  });

  it("reuses the latest timestamp through the Hermes runtime checkpoint", async () => {
    const client = new FakeMotiveClient();
    const connector = new MotiveConnector(client, {
      connectorId: "motive-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      credentialReference: "secret://motive",
      resources: ["vehicle"],
    });
    const registry = new ConnectorRegistry();
    registry.register(connector);
    const runtime = new ConnectorRuntime(
      registry,
      new InMemoryCheckpointStore(),
      { maxAttempts: 1, delayMs: 0 },
    );

    await runtime.synchronize("motive-primary", context, SynchronizationMode.Incremental, "corr-1");
    await runtime.synchronize("motive-primary", context, SynchronizationMode.Incremental, "corr-2");

    expect(client.updatedAfterValues).toEqual([undefined, "2026-07-24T12:00:00.000Z"]);
  });

  it("reports health and disconnects cleanly", async () => {
    const client = new FakeMotiveClient();
    const connector = new MotiveConnector(client, {
      connectorId: "motive-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      resources: ["ifta-summary"],
    });

    await connector.connect(context);
    const health = await connector.health(context);
    await connector.disconnect(context);

    expect(health.status).toBe("healthy");
    expect(client.disconnected).toBe(true);
  });
});
