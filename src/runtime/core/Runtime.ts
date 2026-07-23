import { randomUUID } from "node:crypto";
import { ExecutionContext, RuntimeLogger } from "./ExecutionContext";
import { IRuntime } from "./IRuntime";
import { IWorker } from "./IWorker";
import { WorkerResult } from "./WorkerResult";

const consoleLogger: RuntimeLogger = {
  info: (message, metadata) => console.info(message, metadata ?? {}),
  error: (message, metadata) => console.error(message, metadata ?? {}),
};

export class Runtime implements IRuntime {
  private readonly workers = new Map<string, IWorker>();

  constructor(private readonly logger: RuntimeLogger = consoleLogger) {}

  register(worker: IWorker): void {
    const name = worker.definition.name.trim();
    if (!name) {
      throw new Error("Worker name is required.");
    }
    if (this.workers.has(name)) {
      throw new Error(`Worker '${name}' is already registered.`);
    }
    this.workers.set(name, worker);
  }

  async execute<T = unknown>(workerName: string): Promise<WorkerResult<T>> {
    const worker = this.workers.get(workerName);
    if (!worker) {
      return WorkerResult.failure("WORKER_NOT_FOUND", `Worker '${workerName}' is not registered.`) as WorkerResult<T>;
    }

    const jobId = randomUUID();
    const context = new ExecutionContext({
      jobId,
      workerId: worker.definition.name,
      correlationId: jobId,
      attemptNumber: 1,
      startedAt: new Date(),
      logger: this.logger,
    });

    try {
      return (await worker.execute(context)) as WorkerResult<T>;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown worker error.";
      this.logger.error("Worker execution failed.", { workerName, jobId, message });
      return WorkerResult.failure("WORKER_EXECUTION_FAILED", message) as WorkerResult<T>;
    }
  }
}
