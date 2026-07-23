import { ExecutionContext } from "./ExecutionContext";
import { WorkerDefinition } from "./WorkerDefinition";
import { WorkerResult } from "./WorkerResult";

export interface IWorker<T = unknown> {
  readonly definition: WorkerDefinition;
  execute(context: ExecutionContext): Promise<WorkerResult<T>>;
}
