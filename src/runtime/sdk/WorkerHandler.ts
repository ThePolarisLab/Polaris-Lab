import { ExecutionContext } from "../core/ExecutionContext";
import { WorkerResult } from "../core/WorkerResult";

export type WorkerHandlerResult<T> = T | WorkerResult<T> | void | WorkerResult<void>;

export type WorkerHandler<TPayload = unknown, TResult = unknown> = (
  context: ExecutionContext,
  payload: TPayload,
) => Promise<WorkerHandlerResult<TResult>> | WorkerHandlerResult<TResult>;
