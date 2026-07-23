import { EventBus } from "../../src/runtime/events/EventBus";
import { IEvent } from "../../src/runtime/events/IEvent";
import { Runtime } from "../../src/runtime/core/Runtime";
import { HelloPolarisWorker } from "../../src/runtime/workers/HelloPolarisWorker";

interface TestEvent extends IEvent {
  readonly name: "TestEvent";
  readonly value: number;
}

function testEvent(value = 1): TestEvent {
  return {
    id: `event-${value}`,
    name: "TestEvent",
    timestamp: new Date("2026-07-23T12:00:00.000Z"),
    value,
  };
}

describe("EventBus", () => {
  it("delivers an event to named and global subscribers", () => {
    const bus = new EventBus();
    const named = jest.fn();
    const global = jest.fn();

    bus.subscribe<TestEvent>("TestEvent", named);
    bus.subscribeAll(global);
    bus.publish(testEvent());

    expect(named).toHaveBeenCalledTimes(1);
    expect(global).toHaveBeenCalledTimes(1);
  });

  it("returns an idempotent unsubscribe function", () => {
    const bus = new EventBus();
    const handler = jest.fn();
    const unsubscribe = bus.subscribe<TestEvent>("TestEvent", handler);

    unsubscribe();
    unsubscribe();
    bus.publish(testEvent());

    expect(handler).not.toHaveBeenCalled();
  });

  it("does not register the same handler twice", () => {
    const bus = new EventBus();
    const handler = jest.fn();

    bus.subscribe<TestEvent>("TestEvent", handler);
    bus.subscribe<TestEvent>("TestEvent", handler);
    bus.publish(testEvent());

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("isolates subscriber failures and continues delivery", () => {
    const failures: unknown[] = [];
    const bus = new EventBus(({ error }) => failures.push(error));
    const delivered = jest.fn();

    bus.subscribe<TestEvent>("TestEvent", () => {
      throw new Error("subscriber failed");
    });
    bus.subscribe<TestEvent>("TestEvent", delivered);
    bus.publish(testEvent());

    expect(delivered).toHaveBeenCalledTimes(1);
    expect(failures).toHaveLength(1);
  });

  it("preserves subscription order during asynchronous delivery", async () => {
    const bus = new EventBus();
    const order: string[] = [];

    bus.subscribe<TestEvent>("TestEvent", async () => {
      await Promise.resolve();
      order.push("first");
    });
    bus.subscribe<TestEvent>("TestEvent", async () => {
      order.push("second");
    });

    await bus.publishAsync(testEvent());

    expect(order).toEqual(["first", "second"]);
  });

  it("allows Runtime lifecycle events to be observed without Runtime coupling", async () => {
    const bus = new EventBus();
    const names: string[] = [];
    bus.subscribeAll((event) => {
      names.push(event.name);
    });
    const runtime = new Runtime(
      { info: jest.fn(), error: jest.fn() },
      undefined,
      bus,
    );

    runtime.register(new HelloPolarisWorker());
    await runtime.execute("hello-polaris");

    expect(names).toEqual([
      "WorkerCreated",
      "WorkerValidated",
      "WorkerQueued",
      "WorkerDispatched",
      "WorkerStarted",
      "WorkerSucceeded",
      "WorkerCompleted",
    ]);
  });
});
