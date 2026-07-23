import { IEvent } from "../events/IEvent";
import { WorkerState } from "./WorkerState";

export type RuntimeLifecycleEventName =
  | "WorkerCreated"
  | "WorkerValidated"
  | "WorkerQueued"
  | "WorkerDispatched"
  | "WorkerStarted"
  | "WorkerSucceeded"
  | "WorkerFailed"
  | "WorkerCancelled"
  | "WorkerRetryPending"
  | "WorkerTimedOut"
  | "WorkerCompleted";

const eventNames: Readonly<Record<WorkerState, RuntimeLifecycleEventName>> = {
  [WorkerState.Created]: "WorkerCreated",
  [WorkerState.Validated]: "WorkerValidated",
  [WorkerState.Queued]: "WorkerQueued",
  [WorkerState.Dispatching]: "WorkerDispatched",
  [WorkerState.Running]: "WorkerStarted",
  [WorkerState.Succeeded]: "WorkerSucceeded",
  [WorkerState.Failed]: "WorkerFailed",
  [WorkerState.Cancelled]: "WorkerCancelled",
  [WorkerState.RetryPending]: "WorkerRetryPending",
  [WorkerState.TimedOut]: "WorkerTimedOut",
  [WorkerState.Completed]: "WorkerCompleted",
};

export interface RuntimeLifecycleEvent extends IEvent {
  readonly name: RuntimeLifecycleEventName;
  readonly executionId: string;
  readonly workerName: string;
  readonly state: WorkerState;
  readonly reason?: string;
}

export type RuntimeLifecycleEventListener = (event: RuntimeLifecycleEvent) => void;

export function eventNameForState(state: WorkerState): RuntimeLifecycleEventName {
  return eventNames[state];
}
