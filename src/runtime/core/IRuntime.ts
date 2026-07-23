import { IWorker } from "./IWorker";
import { WorkerResult } from "./WorkerResult";

export interface IRuntime {
  register(worker: IWorker): void;
  execute<T = unknown>(workerName: string): Promise<WorkerResult<T>>;
}
