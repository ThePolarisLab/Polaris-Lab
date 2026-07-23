export interface RuntimeLogger {
  info(message: string, metadata?: Readonly<Record<string, unknown>>): void;
  error(message: string, metadata?: Readonly<Record<string, unknown>>): void;
}

export interface ExecutionContextOptions {
  readonly jobId: string;
  readonly workerId: string;
  readonly correlationId: string;
  readonly attemptNumber: number;
  readonly startedAt: Date;
  readonly logger: RuntimeLogger;
}

export class ExecutionContext {
  public readonly jobId: string;
  public readonly workerId: string;
  public readonly correlationId: string;
  public readonly attemptNumber: number;
  public readonly startedAt: Date;
  public readonly logger: RuntimeLogger;

  constructor(options: ExecutionContextOptions) {
    this.jobId = options.jobId;
    this.workerId = options.workerId;
    this.correlationId = options.correlationId;
    this.attemptNumber = options.attemptNumber;
    this.startedAt = new Date(options.startedAt.getTime());
    this.logger = options.logger;

    Object.freeze(this);
  }
}
