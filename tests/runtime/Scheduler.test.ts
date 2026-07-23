import { Dispatcher } from "../../src/runtime/scheduler/Dispatcher";
import { QueuePriority } from "../../src/runtime/scheduler/QueuePriority";
import { Scheduler } from "../../src/runtime/scheduler/Scheduler";

describe("Scheduler", () => {
  it("preserves FIFO order for equal-priority work", () => {
    const scheduler = new Scheduler();
    scheduler.enqueue({ workerName: "first" });
    scheduler.enqueue({ workerName: "second" });

    expect(scheduler.dequeue()?.workerName).toBe("first");
    expect(scheduler.dequeue()?.workerName).toBe("second");
    expect(scheduler.size).toBe(0);
  });

  it("dispatches higher-priority work first", () => {
    const scheduler = new Scheduler();
    scheduler.enqueue({ workerName: "normal", priority: QueuePriority.Normal });
    scheduler.enqueue({ workerName: "critical", priority: QueuePriority.Critical });
    scheduler.enqueue({ workerName: "high", priority: QueuePriority.High });

    expect(scheduler.dequeue()?.workerName).toBe("critical");
    expect(scheduler.dequeue()?.workerName).toBe("high");
    expect(scheduler.dequeue()?.workerName).toBe("normal");
  });

  it("keeps delayed work unavailable until its due time", () => {
    const scheduler = new Scheduler();
    const due = new Date("2026-07-24T10:00:10.000Z");
    scheduler.enqueue({ workerName: "delayed", availableAt: due });

    expect(scheduler.peek(new Date("2026-07-24T10:00:09.999Z"))).toBeUndefined();
    expect(scheduler.dequeue(due)?.workerName).toBe("delayed");
  });

  it("schedules retries with an incremented attempt and delay", () => {
    const scheduler = new Scheduler();
    const original = scheduler.enqueue({
      workerName: "retryable",
      payload: { job: 7 },
      priority: QueuePriority.High,
    });
    scheduler.dequeue();

    const retry = scheduler.scheduleRetry(
      original,
      5_000,
      new Date("2026-07-24T12:00:00.000Z"),
    );

    expect(retry.attemptNumber).toBe(2);
    expect(retry.priority).toBe(QueuePriority.High);
    expect(retry.payload).toEqual({ job: 7 });
    expect(retry.availableAt.toISOString()).toBe("2026-07-24T12:00:05.000Z");
  });

  it("cancels queued work by id", () => {
    const scheduler = new Scheduler();
    const item = scheduler.enqueue({ workerName: "cancel-me" });

    expect(scheduler.cancel(item.id)).toBe(true);
    expect(scheduler.cancel(item.id)).toBe(false);
    expect(scheduler.size).toBe(0);
  });

  it("returns defensive date copies", () => {
    const scheduler = new Scheduler();
    const item = scheduler.enqueue({ workerName: "immutable" });
    item.availableAt.setUTCFullYear(2000);

    expect(scheduler.peek()?.availableAt.getUTCFullYear()).not.toBe(2000);
  });

  it("rejects invalid requests and retry delays", () => {
    const scheduler = new Scheduler();

    expect(() => scheduler.enqueue({ workerName: "   " })).toThrow("Worker name is required");
    const item = scheduler.enqueue({ workerName: "retry" });
    expect(() => scheduler.scheduleRetry(item, -1)).toThrow("Retry delay");
  });
});

describe("Dispatcher", () => {
  it("dispatches available items through the executor", async () => {
    const scheduler = new Scheduler();
    scheduler.enqueue({ workerName: "one" });
    scheduler.enqueue({ workerName: "two" });
    const executor = jest.fn(async (item) => `ran:${item.workerName}`);
    const dispatcher = new Dispatcher(scheduler, executor);

    const results = await dispatcher.drain<string>();

    expect(results.map((entry) => entry.result)).toEqual(["ran:one", "ran:two"]);
    expect(executor).toHaveBeenCalledTimes(2);
    expect(scheduler.size).toBe(0);
  });

  it("does not dispatch delayed items early", async () => {
    const scheduler = new Scheduler();
    scheduler.enqueue({
      workerName: "later",
      availableAt: new Date("2026-07-24T15:00:00.000Z"),
    });
    const executor = jest.fn(async () => "done");
    const dispatcher = new Dispatcher(scheduler, executor);

    const result = await dispatcher.dispatchNext(
      new Date("2026-07-24T14:59:59.999Z"),
    );

    expect(result).toBeUndefined();
    expect(executor).not.toHaveBeenCalled();
    expect(scheduler.size).toBe(1);
  });
});
