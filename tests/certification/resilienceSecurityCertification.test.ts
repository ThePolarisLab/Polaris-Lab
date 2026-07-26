import {
  InMemoryCheckpointStore,
  ResilientCheckpointRunner,
  redactSensitive,
  safeConnectorHealth,
} from "../../src/hermes/resilience";

describe("PGE-009.10.4 resilience and security certification", () => {
  it("recovers from a partial failure using a durable checkpoint", async () => {
    const store = new InMemoryCheckpointStore();
    const runner = new ResilientCheckpointRunner<string>(store);
    const records = [
      { key: "one", value: "one" },
      { key: "two", value: "two" },
      { key: "three", value: "three" },
    ];
    const handled: string[] = [];

    await expect(runner.run("motive:org-1", records, async (record) => {
      if (record.key === "two") throw new Error("temporary connector failure");
      handled.push(record.key);
    })).rejects.toThrow("temporary connector failure");

    expect(await store.load("motive:org-1")).toEqual({
      streamId: "motive:org-1",
      cursor: 1,
      processedKeys: ["one"],
    });

    const recovered = await runner.run("motive:org-1", records, async (record) => {
      handled.push(record.key);
    });

    expect(recovered).toEqual({ processed: 2, skipped: 0, cursor: 3 });
    expect(handled).toEqual(["one", "two", "three"]);
  });

  it("keeps connector and organization checkpoints isolated", async () => {
    const store = new InMemoryCheckpointStore();
    const runner = new ResilientCheckpointRunner<number>(store);

    await runner.run("outlook:org-a", [{ key: "a", value: 1 }], async () => undefined);
    await runner.run("outlook:org-b", [{ key: "b", value: 2 }], async () => undefined);

    expect(await store.load("outlook:org-a")).toEqual({
      streamId: "outlook:org-a",
      cursor: 1,
      processedKeys: ["a"],
    });
    expect(await store.load("outlook:org-b")).toEqual({
      streamId: "outlook:org-b",
      cursor: 1,
      processedKeys: ["b"],
    });
  });

  it("suppresses duplicate work during replay", async () => {
    const store = new InMemoryCheckpointStore();
    await store.save({ streamId: "quickbooks:org-1", cursor: 0, processedKeys: ["invoice-1"] });
    const runner = new ResilientCheckpointRunner<string>(store);
    const handled: string[] = [];

    const result = await runner.run("quickbooks:org-1", [
      { key: "invoice-1", value: "duplicate" },
      { key: "invoice-2", value: "new" },
    ], async (record) => {
      handled.push(record.key);
    });

    expect(result).toEqual({ processed: 1, skipped: 1, cursor: 2 });
    expect(handled).toEqual(["invoice-2"]);
  });

  it("redacts secrets from nested telemetry and bearer text", () => {
    const sanitized = redactSensitive({
      connectorId: "outlook-1",
      authorization: "Bearer abc.def.ghi",
      nested: {
        clientSecret: "super-secret",
        message: "request failed with Bearer token-value",
      },
      safe: "visible",
    });

    expect(sanitized).toEqual({
      connectorId: "outlook-1",
      authorization: "[REDACTED]",
      nested: {
        clientSecret: "[REDACTED]",
        message: "request failed with Bearer [REDACTED]",
      },
      safe: "visible",
    });
    expect(JSON.stringify(sanitized)).not.toContain("super-secret");
    expect(JSON.stringify(sanitized)).not.toContain("abc.def.ghi");
  });

  it("publishes useful health signals without exposing credentials", () => {
    const health = safeConnectorHealth({
      connectorId: "motive-1",
      organizationId: "org-1",
      status: "degraded",
      checkedAt: "2026-07-26T04:00:00.000Z",
      message: "upstream returned 503; Authorization: Bearer unsafe-token",
    });

    expect(health.status).toBe("degraded");
    expect(health.organizationId).toBe("org-1");
    expect(health.message).toBe("upstream returned 503; Authorization: Bearer [REDACTED]");
    expect(JSON.stringify(health)).not.toContain("unsafe-token");
  });
});
