import { RuntimeLogger } from "../../src/runtime/core/ExecutionContext";
import { Runtime } from "../../src/runtime/core/Runtime";
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
