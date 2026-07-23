import { LifecycleRecord } from "./LifecycleRecord";
import { WorkerState } from "./WorkerState";

export interface LifecycleSnapshot {
  readonly current: WorkerState;
  readonly startedAt?: Date;
  readonly completedAt?: Date;
  readonly history: readonly LifecycleRecord[];
}
