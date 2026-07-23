import { LifecycleManager } from "../../src/runtime/lifecycle/LifecycleManager";
import { InvalidLifecycleTransitionError } from "../../src/runtime/lifecycle/TransitionValidator";
import { WorkerState } from "../../src/runtime/lifecycle/WorkerState";

describe("LifecycleManager", () => {
  it("records the successful lifecycle in order", () => {
    const events: string[] = [];
    const lifecycle = new LifecycleManager(
      "execution-1",
      "worker-1",
      (event) => events.push(event.name),
      new Date("2026-07-23T12:00:00.000Z"),
    );

    lifecycle.transition(WorkerState.Validated);
    lifecycle.transition(WorkerState.Queued);
    lifecycle.transition(WorkerState.Dispatching);
    lifecycle.transition(WorkerState.Running, undefined, new Date("2026-07-23T12:00:01.000Z"));
    lifecycle.transition(WorkerState.Succeeded);
    const snapshot = lifecycle.transition(
      WorkerState.Completed,
      undefined,
      new Date("2026-07-23T12:00:02.000Z"),
    );

    expect(snapshot.current).toBe(WorkerState.Completed);
    expect(snapshot.startedAt?.toISOString()).toBe("2026-07-23T12:00:01.000Z");
    expect(snapshot.completedAt?.toISOString()).toBe("2026-07-23T12:00:02.000Z");
    expect(snapshot.history.map((record) => record.state)).toEqual([
      WorkerState.Created,
      WorkerState.Validated,
      WorkerState.Queued,
      WorkerState.Dispatching,
      WorkerState.Running,
      WorkerState.Succeeded,
      WorkerState.Completed,
    ]);
    expect(events).toEqual([
      "WorkerCreated",
      "WorkerValidated",
      "WorkerQueued",
      "WorkerDispatched",
      "WorkerStarted",
      "WorkerSucceeded",
      "WorkerCompleted",
    ]);
  });

  it("rejects illegal transitions without changing state", () => {
    const lifecycle = new LifecycleManager("execution-2", "worker-2");

    expect(() => lifecycle.transition(WorkerState.Running)).toThrow(
      InvalidLifecycleTransitionError,
    );
    expect(lifecycle.currentState).toBe(WorkerState.Created);
    expect(lifecycle.history()).toHaveLength(1);
  });

  it("supports failure, retry, and completion paths", () => {
    const lifecycle = new LifecycleManager("execution-3", "worker-3");

    lifecycle.transition(WorkerState.Validated);
    lifecycle.transition(WorkerState.Queued);
    lifecycle.transition(WorkerState.Dispatching);
    lifecycle.transition(WorkerState.Running);
    lifecycle.transition(WorkerState.Failed, "Temporary dependency failure");
    lifecycle.transition(WorkerState.RetryPending);
    lifecycle.transition(WorkerState.Queued);
    lifecycle.transition(WorkerState.Dispatching);
    lifecycle.transition(WorkerState.Running);
    lifecycle.transition(WorkerState.Succeeded);
    const snapshot = lifecycle.transition(WorkerState.Completed);

    expect(snapshot.current).toBe(WorkerState.Completed);
    expect(snapshot.history.some((record) => record.state === WorkerState.RetryPending)).toBe(true);
  });

  it("returns defensive copies of lifecycle history", () => {
    const lifecycle = new LifecycleManager("execution-4", "worker-4");
    const history = lifecycle.history();

    history[0].timestamp.setUTCFullYear(2000);

    expect(lifecycle.history()[0].timestamp.getUTCFullYear()).not.toBe(2000);
  });
});
