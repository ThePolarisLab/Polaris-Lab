import { Runtime } from "../../src/runtime/core/Runtime";
import { WorkerResult } from "../../src/runtime/core/WorkerResult";
import { defineWorker } from "../../src/runtime/sdk/WorkerFactory";
import { WorkerRegistry } from "../../src/runtime/sdk/WorkerRegistry";

const logger = { info: jest.fn(), error: jest.fn() };

describe("Worker SDK", () => {
  it("creates and executes a worker from a handler", async () => {
    const worker = defineWorker<number, number>({
      name: "double",
      version: "1.0.0",
      defaultPayload: 21,
      handler: (_context, payload) => payload * 2,
    });
    const runtime = new Runtime(logger);
    runtime.register(worker);

    const result = await runtime.execute<number>("double");

    expect(result.succeeded).toBe(true);
    expect(result.value).toBe(42);
    expect(Object.isFrozen(worker)).toBe(true);
    expect(Object.isFrozen(worker.definition)).toBe(true);
  });

  it("preserves explicit WorkerResult failures", async () => {
    const worker = defineWorker<void, never>({
      name: "sdk-failure",
      version: "1.0.0",
      handler: () => WorkerResult.failure("EXPECTED", "Expected failure", true),
    });
    const result = await worker.execute({} as never);

    expect(result.succeeded).toBe(false);
    expect(result.error).toEqual({ code: "EXPECTED", message: "Expected failure", retryable: true });
  });

  it("validates worker identity", () => {
    expect(() => defineWorker({ name: " ", version: "1.0.0", handler: () => undefined }))
      .toThrow("Worker name is required");
    expect(() => defineWorker({ name: "valid", version: " ", handler: () => undefined }))
      .toThrow("Worker version is required");
  });

  it("registers, lists, and installs workers into Runtime", async () => {
    const first = defineWorker({ name: "first-sdk", version: "1.0.0", handler: () => "first" });
    const second = defineWorker({ name: "second-sdk", version: "1.0.0", handler: () => "second" });
    const registry = new WorkerRegistry();
    registry.register(first);
    registry.register(second);

    expect(registry.has("first-sdk")).toBe(true);
    expect(registry.get("second-sdk")).toBe(second);
    expect(registry.list().map((worker) => worker.definition.name)).toEqual(["first-sdk", "second-sdk"]);
    expect(Object.isFrozen(registry.list())).toBe(true);
    expect(() => registry.register(first)).toThrow("already registered");

    const runtime = new Runtime(logger);
    registry.install(runtime);
    expect((await runtime.execute<string>("second-sdk")).value).toBe("second");
  });
});
