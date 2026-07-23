import { randomUUID } from "node:crypto";
import { LifecycleManager } from "../lifecycle/LifecycleManager";
import { LifecycleSnapshot } from "../lifecycle/LifecycleSnapshot";
import { RuntimeLifecycleEventListener } from "../lifecycle/RuntimeEvents";
import { WorkerState } from "../lifecycle/WorkerState";
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
  private latestLifecycle?: LifecycleSnapshot;

  constructor(
    private readonly logger: RuntimeLogger = consoleLogger,
    private readonly lifecycleListener?: RuntimeLifecycleEventListener,
  ) {}

  get lastLifecycle(): LifecycleSnapshot | undefined {
    return this.latestLifecycle;
  }

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
    const lifecycle = new LifecycleManager(jobId, worker.definition.name, this.lifecycleListener);
    lifecycle.transition(WorkerState.Validated);
    lifecycle.transition(WorkerState.Queued);
    lifecycle.transition(WorkerState.Dispatching);
    lifecycle.transition(WorkerState.Running);

    const context = new ExecutionContext({
      jobId,
      workerId: worker.definition.name,
      correlationId: jobId,
      attemptNumber: 1,
      startedAt: new Date(),
      logger: this.logger,
    });

    try {
      const result = (await worker.execute(context)) as WorkerResult<T>;
      if (result.succeeded) {
        lifecycle.transition(WorkerState.Succeeded);
      } else {
        lifecycle.transition(WorkerState.Failed, result.error?.message);
      }
      this.latestLifecycle = lifecycle.transition(WorkerState.Completed);
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown worker error.";
      this.logger.error("Worker execution failed.", { workerName, jobId, message });
      lifecycle.transition(WorkerState.Failed, message);
      this.latestLifecycle = lifecycle.transition(WorkerState.Completed);
      return WorkerResult.failure("WORKER_EXECUTION_FAILED", message) as WorkerResult<T>;
    }
  }
}
