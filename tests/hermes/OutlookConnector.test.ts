import { ConnectorRuntime } from "../../src/hermes/runtime/ConnectorRuntime";
import { ConnectorRegistry } from "../../src/hermes/runtime/ConnectorRegistry";
import { InMemoryCheckpointStore } from "../../src/hermes/runtime/CheckpointStore";
import { SynchronizationMode } from "../../src/hermes/connectors/contracts";
import {
  GraphMailClient,
  OutlookConnector,
  OutlookDeltaPage,
} from "../../src/hermes/connectors/outlook";

class FakeGraphMailClient implements GraphMailClient {
  public authenticatedWith?: string;
  public disconnected = false;
  public readonly cursors: Array<string | undefined> = [];

  public async authenticate(credentialReference?: string): Promise<void> {
    this.authenticatedWith = credentialReference;
  }

  public async listFolders() {
    return [{ id: "inbox", displayName: "Inbox" }];
  }

  public async listMessagesDelta(cursor?: string): Promise<OutlookDeltaPage> {
    this.cursors.push(cursor);
    if (!cursor) {
      return {
        messages: [{
          id: "m-1",
          subject: "Dispatch update",
          toRecipients: ["ops@example.com"],
          ccRecipients: [],
          receivedAt: "2026-07-24T12:00:00.000Z",
          hasAttachments: true,
          attachments: [{ id: "a-1", name: "bol.pdf", contentType: "application/pdf" }],
        }],
        deltaLink: "delta-1",
      };
    }

    return {
      messages: [{
        id: "m-2",
        subject: "Invoice received",
        toRecipients: ["accounts@example.com"],
        ccRecipients: [],
        receivedAt: "2026-07-24T13:00:00.000Z",
        hasAttachments: false,
        attachments: [],
      }],
      deltaLink: "delta-2",
    };
  }

  public async disconnect(): Promise<void> {
    this.disconnected = true;
  }
}

const scope = { organizationId: "org-1", tenantId: "tenant-1" };
const context = {
  scope,
  correlationId: "corr-1",
  credentialReference: "secret://outlook",
};

describe("OutlookConnector", () => {
  it("authenticates, discovers folders, and emits Outlook evidence", async () => {
    const client = new FakeGraphMailClient();
    const connector = new OutlookConnector(client, {
      connectorId: "outlook-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
    });

    await connector.connect(context);
    const result = await connector.synchronize({
      scope,
      mode: SynchronizationMode.Full,
      requestedAt: "2026-07-24T14:00:00.000Z",
      correlationId: "corr-1",
    });

    expect(client.authenticatedWith).toBe("secret://outlook");
    expect(connector.discoveredFolders).toHaveLength(1);
    expect(result.evidence).toHaveLength(1);
    expect(result.evidence[0].payload.message.attachments[0].name).toBe("bol.pdf");
    expect(result.checkpoint?.cursor).toBe("delta-1");
  });

  it("uses the runtime checkpoint for the next incremental synchronization", async () => {
    const client = new FakeGraphMailClient();
    const connector = new OutlookConnector(client, {
      connectorId: "outlook-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
      credentialReference: "secret://outlook",
    });
    const registry = new ConnectorRegistry();
    registry.register(connector);
    const runtime = new ConnectorRuntime(registry, new InMemoryCheckpointStore(), { maxAttempts: 1, delayMs: 0 });

    await runtime.synchronize("outlook-primary", context, SynchronizationMode.Incremental, "corr-1");
    const second = await runtime.synchronize("outlook-primary", context, SynchronizationMode.Incremental, "corr-2");

    expect(client.cursors).toEqual([undefined, "delta-1"]);
    expect(second.evidence[0].source.sourceRecordId).toBe("m-2");
    expect(second.checkpoint?.cursor).toBe("delta-2");
  });

  it("disconnects the Graph client and clears folder discovery", async () => {
    const client = new FakeGraphMailClient();
    const connector = new OutlookConnector(client, {
      connectorId: "outlook-primary",
      organizationId: scope.organizationId,
      tenantId: scope.tenantId,
    });

    await connector.connect(context);
    await connector.disconnect(context);

    expect(client.disconnected).toBe(true);
    expect(connector.discoveredFolders).toHaveLength(0);
  });
});
