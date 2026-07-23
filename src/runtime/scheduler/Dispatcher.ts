import { QueueItem } from "./QueueItem";
import { IScheduler } from "./IScheduler";

export type QueueExecutor<TResult = unknown> = (item: QueueItem) => Promise<TResult>;

export interface DispatchResult<TResult = unknown> {
  readonly item: QueueItem;
  readonly result: TResult;
}

export class Dispatcher {
  constructor(
    private readonly scheduler: IScheduler,
    private readonly executor: QueueExecutor,
  ) {}

  async dispatchNext<TResult = unknown>(now: Date = new Date()): Promise<DispatchResult<TResult> | undefined> {
    const item = this.scheduler.dequeue(now);
    if (!item) {
      return undefined;
    }

    const result = (await this.executor(item)) as TResult;
    return { item, result };
  }

  async drain<TResult = unknown>(now: Date = new Date()): Promise<readonly DispatchResult<TResult>[]> {
    const results: DispatchResult<TResult>[] = [];
    while (true) {
      const dispatched = await this.dispatchNext<TResult>(now);
      if (!dispatched) {
        return results;
      }
      results.push(dispatched);
    }
  }
}
