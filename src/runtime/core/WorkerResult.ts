export type WorkerResultStatus = "success" | "failure";

export interface WorkerFailure {
  readonly code: string;
  readonly message: string;
  readonly retryable: boolean;
}

export class WorkerResult<T = unknown> {
  private constructor(
    public readonly status: WorkerResultStatus,
    public readonly value: T | undefined,
    public readonly error: WorkerFailure | undefined,
  ) {}

  static success<T = unknown>(value?: T): WorkerResult<T> {
    return new WorkerResult<T>("success", value, undefined);
  }

  static failure(
    code: string,
    message: string,
    retryable = false,
  ): WorkerResult<never> {
    return new WorkerResult<never>("failure", undefined, {
      code,
      message,
      retryable,
    });
  }

  get succeeded(): boolean {
    return this.status === "success";
  }
}
