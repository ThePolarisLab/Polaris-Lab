import { QueuePriority } from "./QueuePriority";

export interface QueueItem<TPayload = unknown> {
  readonly id: string;
  readonly workerName: string;
  readonly payload?: TPayload;
  readonly priority: QueuePriority;
  readonly attemptNumber: number;
  readonly enqueuedAt: Date;
  readonly availableAt: Date;
}

export interface EnqueueRequest<TPayload = unknown> {
  readonly workerName: string;
  readonly payload?: TPayload;
  readonly priority?: QueuePriority;
  readonly attemptNumber?: number;
  readonly availableAt?: Date;
}
