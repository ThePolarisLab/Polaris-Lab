import { WorkerState } from "./WorkerState";

const allowedTransitions: Readonly<Record<WorkerState, readonly WorkerState[]>> = {
  [WorkerState.Created]: [WorkerState.Validated, WorkerState.Cancelled],
  [WorkerState.Validated]: [WorkerState.Queued, WorkerState.Cancelled],
  [WorkerState.Queued]: [WorkerState.Dispatching, WorkerState.Cancelled],
  [WorkerState.Dispatching]: [WorkerState.Running, WorkerState.Failed, WorkerState.Cancelled],
  [WorkerState.Running]: [
    WorkerState.Succeeded,
    WorkerState.Failed,
    WorkerState.Cancelled,
    WorkerState.TimedOut,
  ],
  [WorkerState.Succeeded]: [WorkerState.Completed],
  [WorkerState.Failed]: [WorkerState.RetryPending, WorkerState.Completed],
  [WorkerState.Cancelled]: [WorkerState.Completed],
  [WorkerState.RetryPending]: [WorkerState.Queued, WorkerState.Cancelled],
  [WorkerState.TimedOut]: [WorkerState.RetryPending, WorkerState.Completed],
  [WorkerState.Completed]: [],
};

export class InvalidLifecycleTransitionError extends Error {
  constructor(
    public readonly from: WorkerState,
    public readonly to: WorkerState,
  ) {
    super(`Invalid worker lifecycle transition: ${from} -> ${to}.`);
    this.name = "InvalidLifecycleTransitionError";
  }
}

export class TransitionValidator {
  static isAllowed(from: WorkerState, to: WorkerState): boolean {
    return allowedTransitions[from].includes(to);
  }

  static assertAllowed(from: WorkerState, to: WorkerState): void {
    if (!this.isAllowed(from, to)) {
      throw new InvalidLifecycleTransitionError(from, to);
    }
  }
}
