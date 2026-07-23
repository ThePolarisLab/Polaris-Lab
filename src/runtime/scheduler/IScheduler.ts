import { EnqueueRequest, QueueItem } from "./QueueItem";

export interface IScheduler {
  readonly size: number;
  enqueue<TPayload = unknown>(request: EnqueueRequest<TPayload>): QueueItem<TPayload>;
  peek(now?: Date): QueueItem | undefined;
  dequeue(now?: Date): QueueItem | undefined;
  cancel(itemId: string): boolean;
}
