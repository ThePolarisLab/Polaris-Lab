import { ExecutionContext } from "../core/ExecutionContext";
import { IWorker } from "../core/IWorker";
import { WorkerDefinition } from "../core/WorkerDefinition";
import { WorkerResult } from "../core/WorkerResult";
import { WorkerHandler } from "./WorkerHandler";

export interface WorkerOptions<TPayload = unknown, TResult = unknown> extends WorkerDefinition {
  readonly handler: WorkerHandler<TPayload, TResult>;
  readonly defaultPayload?: TPayload;
}

export function defineWorker<TPayload = unknown, TResult = unknown>(
  options: WorkerOptions<TPayload, TResult>,
): IWorker<TResult> {
  const name = options.name.trim();
  const version = options.version.trim();
  if (!name) throw new Error("Worker name is required.");
  if (!version) throw new Error("Worker version is required.");

  const definition: WorkerDefinition = Object.freeze({
    name,
    version,
    ...(options.description?.trim() ? { description: options.description.trim() } : {}),
  });

  return Object.freeze({
    definition,
    async execute(context: ExecutionContext): Promise<WorkerResult<TResult>> {
      const output = await options.handler(context, options.defaultPayload as TPayload);
      if (output instanceof WorkerResult) return output as WorkerResult<TResult>;
      return WorkerResult.success(output as TResult);
    },
  });
}
