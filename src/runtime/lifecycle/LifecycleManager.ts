import { LifecycleRecord } from "./LifecycleRecord";
import { LifecycleSnapshot } from "./LifecycleSnapshot";
import {
  eventNameForState,
  RuntimeLifecycleEventListener,
} from "./RuntimeEvents";
import { TransitionValidator } from "./TransitionValidator";
import { WorkerState } from "./WorkerState";

export class LifecycleManager {
  private current: WorkerState = WorkerState.Created;
  private readonly records: LifecycleRecord[];

  constructor(
    private readonly executionId: string,
    private readonly workerName: string,
    private readonly listener?: RuntimeLifecycleEventListener,
    createdAt: Date = new Date(),
  ) {
    const initialRecord: LifecycleRecord = {
      state: WorkerState.Created,
      timestamp: new Date(createdAt),
    };
    this.records = [initialRecord];
    this.emit(initialRecord);
  }

  get currentState(): WorkerState {
    return this.current;
  }

  transition(to: WorkerState, reason?: string, at: Date = new Date()): LifecycleSnapshot {
    TransitionValidator.assertAllowed(this.current, to);

    const record: LifecycleRecord = {
      state: to,
      timestamp: new Date(at),
      ...(reason ? { reason } : {}),
    };

    this.current = to;
    this.records.push(record);
    this.emit(record);
    return this.snapshot();
  }

  history(): readonly LifecycleRecord[] {
    return this.records.map((record) => this.cloneRecord(record));
  }

  snapshot(): LifecycleSnapshot {
    const started = this.records.find((record) => record.state === WorkerState.Running);
    const completed = this.records.find((record) => record.state === WorkerState.Completed);

    return {
      current: this.current,
      ...(started ? { startedAt: new Date(started.timestamp) } : {}),
      ...(completed ? { completedAt: new Date(completed.timestamp) } : {}),
      history: this.history(),
    };
  }

  private emit(record: LifecycleRecord): void {
    this.listener?.({
      name: eventNameForState(record.state),
      executionId: this.executionId,
      workerName: this.workerName,
      state: record.state,
      timestamp: new Date(record.timestamp),
      ...(record.reason ? { reason: record.reason } : {}),
    });
  }

  private cloneRecord(record: LifecycleRecord): LifecycleRecord {
    return {
      state: record.state,
      timestamp: new Date(record.timestamp),
      ...(record.reason ? { reason: record.reason } : {}),
    };
  }
}
