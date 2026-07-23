import { randomUUID } from "node:crypto";
import { IScheduler } from "./IScheduler";
import { EnqueueRequest, QueueItem } from "./QueueItem";
import { QueuePriority } from "./QueuePriority";

interface ScheduledEntry {
  readonly item: QueueItem;
  readonly sequence: number;
}

export class Scheduler implements IScheduler {
  private readonly entries: ScheduledEntry[] = [];
  private sequence = 0;

  get size(): number {
    return this.entries.length;
  }

  enqueue<TPayload = unknown>(request: EnqueueRequest<TPayload>): QueueItem<TPayload> {
    const workerName = request.workerName.trim();
    if (!workerName) {
      throw new Error("Worker name is required.");
    }

    const now = new Date();
    const item: QueueItem<TPayload> = {
      id: randomUUID(),
      workerName,
      ...(request.payload === undefined ? {} : { payload: request.payload }),
      priority: request.priority ?? QueuePriority.Normal,
      attemptNumber: request.attemptNumber ?? 1,
      enqueuedAt: now,
      availableAt: new Date(request.availableAt ?? now),
    };

    this.entries.push({ item, sequence: this.sequence++ });
    return this.clone(item);
  }

  peek(now: Date = new Date()): QueueItem | undefined {
    const entry = this.nextAvailable(now);
    return entry ? this.clone(entry.item) : undefined;
  }

  dequeue(now: Date = new Date()): QueueItem | undefined {
    const entry = this.nextAvailable(now);
    if (!entry) {
      return undefined;
    }

    const index = this.entries.indexOf(entry);
    this.entries.splice(index, 1);
    return this.clone(entry.item);
  }

  cancel(itemId: string): boolean {
    const index = this.entries.findIndex((entry) => entry.item.id === itemId);
    if (index < 0) {
      return false;
    }
    this.entries.splice(index, 1);
    return true;
  }

  scheduleRetry<TPayload = unknown>(
    item: QueueItem<TPayload>,
    delayMs: number,
    now: Date = new Date(),
  ): QueueItem<TPayload> {
    if (!Number.isFinite(delayMs) || delayMs < 0) {
      throw new Error("Retry delay must be a non-negative finite number.");
    }

    return this.enqueue({
      workerName: item.workerName,
      ...(item.payload === undefined ? {} : { payload: item.payload }),
      priority: item.priority,
      attemptNumber: item.attemptNumber + 1,
      availableAt: new Date(now.getTime() + delayMs),
    });
  }

  private nextAvailable(now: Date): ScheduledEntry | undefined {
    return this.entries
      .filter((entry) => entry.item.availableAt.getTime() <= now.getTime())
      .sort((left, right) => {
        const priority = right.item.priority - left.item.priority;
        if (priority !== 0) {
          return priority;
        }

        const available = left.item.availableAt.getTime() - right.item.availableAt.getTime();
        if (available !== 0) {
          return available;
        }

        return left.sequence - right.sequence;
      })[0];
  }

  private clone<TPayload>(item: QueueItem<TPayload>): QueueItem<TPayload> {
    return {
      id: item.id,
      workerName: item.workerName,
      ...(item.payload === undefined ? {} : { payload: item.payload }),
      priority: item.priority,
      attemptNumber: item.attemptNumber,
      enqueuedAt: new Date(item.enqueuedAt),
      availableAt: new Date(item.availableAt),
    };
  }
}
