export interface Checkpoint {
  readonly streamId: string;
  readonly cursor: number;
  readonly processedKeys: readonly string[];
}

export interface CheckpointStore {
  load(streamId: string): Promise<Checkpoint | undefined>;
  save(checkpoint: Checkpoint): Promise<void>;
}

export class InMemoryCheckpointStore implements CheckpointStore {
  private readonly checkpoints = new Map<string, Checkpoint>();

  async load(streamId: string): Promise<Checkpoint | undefined> {
    return this.checkpoints.get(streamId);
  }

  async save(checkpoint: Checkpoint): Promise<void> {
    this.checkpoints.set(checkpoint.streamId, Object.freeze({
      ...checkpoint,
      processedKeys: Object.freeze([...checkpoint.processedKeys]),
    }));
  }
}

export interface ResilientRecord<T> {
  readonly key: string;
  readonly value: T;
}

export interface ResilientRunResult {
  readonly processed: number;
  readonly skipped: number;
  readonly cursor: number;
}

export class ResilientCheckpointRunner<T> {
  constructor(private readonly checkpoints: CheckpointStore) {}

  async run(
    streamId: string,
    records: readonly ResilientRecord<T>[],
    handler: (record: ResilientRecord<T>) => Promise<void>,
  ): Promise<ResilientRunResult> {
    const checkpoint = await this.checkpoints.load(streamId);
    const processedKeys = new Set(checkpoint?.processedKeys ?? []);
    let cursor = checkpoint?.cursor ?? 0;
    let processed = 0;
    let skipped = 0;

    for (let index = cursor; index < records.length; index += 1) {
      const record = records[index];
      if (processedKeys.has(record.key)) {
        skipped += 1;
        cursor = index + 1;
        await this.checkpoints.save({ streamId, cursor, processedKeys: [...processedKeys] });
        continue;
      }

      await handler(record);
      processedKeys.add(record.key);
      processed += 1;
      cursor = index + 1;
      await this.checkpoints.save({ streamId, cursor, processedKeys: [...processedKeys] });
    }

    return Object.freeze({ processed, skipped, cursor });
  }
}

const sensitiveKey = /^(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password|secret)$/i;
const bearerToken = /Bearer\s+[A-Za-z0-9._~+\/-]+=*/gi;

export function redactSensitive(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redactSensitive);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, entry]) => [
      key,
      sensitiveKey.test(key) ? "[REDACTED]" : redactSensitive(entry),
    ]));
  }
  if (typeof value === "string") {
    return value.replace(bearerToken, "Bearer [REDACTED]");
  }
  return value;
}

export type ConnectorHealthStatus = "healthy" | "degraded" | "failed";

export interface ConnectorHealth {
  readonly connectorId: string;
  readonly organizationId: string;
  readonly status: ConnectorHealthStatus;
  readonly checkedAt: string;
  readonly message?: string;
}

export function safeConnectorHealth(health: ConnectorHealth): ConnectorHealth {
  const sanitized = redactSensitive(health) as ConnectorHealth;
  return Object.freeze({ ...sanitized });
}
