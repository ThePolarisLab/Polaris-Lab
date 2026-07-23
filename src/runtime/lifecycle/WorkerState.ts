export enum WorkerState {
  Created = "Created",
  Validated = "Validated",
  Queued = "Queued",
  Dispatching = "Dispatching",
  Running = "Running",
  Succeeded = "Succeeded",
  Failed = "Failed",
  Cancelled = "Cancelled",
  RetryPending = "RetryPending",
  TimedOut = "TimedOut",
  Completed = "Completed",
}
