import { ExecutionContext, RuntimeLogger } from "../../src/runtime/core/ExecutionContext";
import { IWorker } from "../../src/runtime/core/IWorker";
import { Runtime } from "../../src/runtime/core/Runtime";
import { WorkerResult } from "../../src/runtime/core/WorkerResult";
import { WorkerState } from "../../src/runtime/lifecycle/WorkerState";
import { HelloPolarisWorker } from "../../src/runtime/workers/HelloPolarisWorker";

describe("Runtime", () => {
  it("executes HelloPolarisWorker successfully", async () => {
    const logger: RuntimeLogger = {
      info: jest.fn(),
      error: jest.fn(),
    };
    const runtime = new Runtime(logger);

    runtime.register(new HelloPolarisWorker());
    const result = await runtime.execute<string>("hello-polaris");

    expect(result.succeeded).toBe(true);
    expect(result.value).toBe("Hello Polaris");
    expect(logger.info).toHaveBeenCalledWith(
      "Hello Polaris",
      expect.objectContaining({
        jobId: expect.any(String),
        correlationId: expect.any(String),
      }),
    );
    expect(runtime.lastLifecycle?.current).toBe(WorkerState.Completed);
  });

  it("emits the complete successful lifecycle in order", async () => {
    const events: string[] = [];
    const runtime = new Runtime(
      { info: jest.fn(), error: jest.fn() },
      (event) => events.push(event.name),
    );

    runtime.register(new HelloPolarisWorker());
    await runtime.execute("hello-polaris");

    expect(events).toEqual([
      "WorkerCreated",
      "WorkerValidated",
      "WorkerQueued",
      "WorkerDispatched",
      "WorkerStarted",
      "WorkerSucceeded",
      "WorkerCompleted",
    ]);
  });

  it("records a failed worker result before completion", async () => {
    const events: string[] = [];
    const failingWorker: IWorker = {
      definition: { name: "failing-worker", version: "1.0.0" },
      execute: async (_context: ExecutionContext) =>
        WorkerResult.failure("EXPECTED_FAILURE", "Expected failure"),
    };
    const runtime = new Runtime(
      { info: jest.fn(), error: jest.fn() },
      (event) => events.push(event.name),
    );

    runtime.register(failingWorker);
    const result = await runtime.execute("failing-worker");

    expect(result.succeeded).toBe(false);
    expect(events.slice(-2)).toEqual(["WorkerFailed", "WorkerCompleted"]);
  });

  it("returns a failure for an unknown worker", async () => {
    const runtime = new Runtime({ info: jest.fn(), error: jest.fn() });

    const result = await runtime.execute("missing-worker");

    expect(result.succeeded).toBe(false);
    expect(result.error?.code).toBe("WORKER_NOT_FOUND");
  });

  it("rejects duplicate worker registrations", () => {
    const runtime = new Runtime({ info: jest.fn(), error: jest.fn() });
    const worker = new HelloPolarisWorker();

    runtime.register(worker);

    expect(() => runtime.register(worker)).toThrow("already registered");
  });
});
