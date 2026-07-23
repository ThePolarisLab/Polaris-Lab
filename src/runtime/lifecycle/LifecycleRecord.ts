import { WorkerState } from "./WorkerState";

export interface LifecycleRecord {
  readonly state: WorkerState;
  readonly timestamp: Date;
  readonly reason?: string;
}
