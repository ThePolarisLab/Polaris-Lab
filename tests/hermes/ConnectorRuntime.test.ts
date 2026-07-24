import {
  ConnectorCapability,
  ConnectorContext,
  ConnectorHealthStatus,
  ConnectorState,
  IConnector,
  SynchronizationMode,
  SynchronizationRequest,
  SynchronizationResult,
} from "../../src/hermes/connectors/contracts";
import {
  ConnectorRegistry,
  ConnectorRuntime,
  InMemoryCheckpointStore,
  RuntimeEvent,
} from "../../src/hermes/runtime";

const scope = { organizationId: "org-1", tenantId: "tenant-1" };
const context: ConnectorContext = { scope, correlationId: "ctx-1" };

class TestConnector implements IConnector<{ value: number }> {
  public state = ConnectorState.Ready;
  public attempts = 0;
  public received: SynchronizationRequest[] = [];
  public failuresBeforeSuccess = 0;

  public readonly descriptor = {
    identity: { id: "test", provider: "test", displayName: "Test", version: "1.0.0" },
    scope,
    capabilities: [ConnectorCapability.Read, ConnectorCapability.IncrementalSync],
    supportedSyncModes: [SynchronizationMode.Full, SynchronizationMode.Incremental],
  };

  public async connect(): Promise<void> { this.state = ConnectorState.Connected; }
  public async disconnect(): Promise<void> { this.state = ConnectorState.Disconnected; }
  public async health() {
    return { connectorId: "test", scope, status: ConnectorHealthStatus.Healthy, state: this.state, checkedAt: new Date().toISOString() };
  }

  public async synchronize(request: SynchronizationRequest): Promise<SynchronizationResult<{ value: number }>> {
    this.attempts += 1;
    this.received.push(request);
    if (this.attempts <= this.failuresBeforeSuccess) {
      this.state = ConnectorState.Failed;
      throw new Error("temporary failure");
    }
    this.state = ConnectorState.Connected;
    return {
      connectorId: "test",
      scope,
      startedAt: request.requestedAt,
      completedAt: new Date().toISOString(),
      mode: request.mode,
      evidence: [],
      failures: [],
      checkpoint: { cursor: `cursor-${this.attempts}`, observedAt: new Date().toISOString(), schemaVersion: "1" },
      partial: false,
    };
  }
}

describe("Hermes connector orchestration runtime", () => {
  test("registers and discovers connectors by capability", () => {
    const registry = new ConnectorRegistry();
    const connector = new TestConnector();
    registry.register(connector);
    expect(registry.get("test")).toBe(connector);
    expect(registry.findByCapability(ConnectorCapability.IncrementalSync)).toEqual([connector]);
    expect(() => registry.register(connector)).toThrow("already registered");
  });

  test("persists and supplies checkpoints for incremental synchronization", async () => {
    const registry = new ConnectorRegistry();
    const connector = new TestConnector();
    registry.register(connector);
    const runtime = new ConnectorRuntime(registry, new InMemoryCheckpointStore(), { maxAttempts: 1, delayMs: 0 });

    await runtime.synchronize("test", context, SynchronizationMode.Incremental, "sync-1");
    await runtime.synchronize("test", context, SynchronizationMode.Incremental, "sync-2");

    expect(connector.received[0].checkpoint).toBeUndefined();
    expect(connector.received[1].checkpoint?.cursor).toBe("cursor-1");
  });

  test("reconnects and retries failed synchronization attempts", async () => {
    const registry = new ConnectorRegistry();
    const connector = new TestConnector();
    connector.failuresBeforeSuccess = 1;
    registry.register(connector);
    const events: RuntimeEvent[] = [];
    const runtime = new ConnectorRuntime(registry, undefined, { maxAttempts: 2, delayMs: 0 }, (event) => events.push(event));

    const result = await runtime.synchronize("test", context, SynchronizationMode.Full, "sync-retry");

    expect(result.checkpoint?.cursor).toBe("cursor-2");
    expect(connector.attempts).toBe(2);
    expect(events.map((event) => event.type)).toEqual(["sync-started", "sync-failed", "sync-started", "sync-succeeded"]);
  });
});
