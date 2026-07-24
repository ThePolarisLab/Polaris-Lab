import {
  ConnectorContext,
  ConnectorId,
  ConnectorState,
  SynchronizationMode,
  SynchronizationRequest,
  SynchronizationResult,
} from "../connectors/contracts";
import { CheckpointStore, InMemoryCheckpointStore } from "./CheckpointStore";
import { ConnectorRegistry } from "./ConnectorRegistry";

export interface RetryPolicy {
  readonly maxAttempts: number;
  readonly delayMs: number;
}

export interface RuntimeEvent {
  readonly type: "sync-started" | "sync-succeeded" | "sync-failed";
  readonly connectorId: ConnectorId;
  readonly correlationId: string;
  readonly occurredAt: string;
  readonly attempt: number;
}

export type RuntimeEventSink = (event: RuntimeEvent) => void;

export class ConnectorRuntime {
  public constructor(
    private readonly registry: ConnectorRegistry,
    private readonly checkpoints: CheckpointStore = new InMemoryCheckpointStore(),
    private readonly retry: RetryPolicy = { maxAttempts: 3, delayMs: 0 },
    private readonly publish: RuntimeEventSink = () => undefined,
  ) {
    if (retry.maxAttempts < 1) throw new Error("maxAttempts must be at least 1");
  }

  public async synchronize(
    connectorId: ConnectorId,
    context: ConnectorContext,
    mode: SynchronizationMode,
    correlationId: string,
  ): Promise<SynchronizationResult> {
    const connector = this.registry.get(connectorId);
    if (connector.state !== ConnectorState.Connected && connector.state !== ConnectorState.Degraded) {
      await connector.connect(context);
    }

    const checkpoint = mode === SynchronizationMode.Incremental
      ? await this.checkpoints.load(connectorId, context.scope)
      : undefined;

    const request: SynchronizationRequest = {
      scope: context.scope,
      mode,
      requestedAt: new Date().toISOString(),
      correlationId,
      checkpoint,
    };

    let lastError: unknown;
    for (let attempt = 1; attempt <= this.retry.maxAttempts; attempt += 1) {
      this.emit("sync-started", connectorId, correlationId, attempt);
      try {
        const result = await connector.synchronize(request);
        if (result.checkpoint) await this.checkpoints.save(connectorId, context.scope, result.checkpoint);
        this.emit("sync-succeeded", connectorId, correlationId, attempt);
        return result;
      } catch (error) {
        lastError = error;
        this.emit("sync-failed", connectorId, correlationId, attempt);
        if (attempt < this.retry.maxAttempts) {
          await connector.disconnect(context);
          if (this.retry.delayMs > 0) {
            await new Promise((resolve) => setTimeout(resolve, this.retry.delayMs));
          }
          await connector.connect(context);
        }
      }
    }

    throw lastError;
  }

  public async disconnect(connectorId: ConnectorId, context: ConnectorContext): Promise<void> {
    await this.registry.get(connectorId).disconnect(context);
  }

  private emit(type: RuntimeEvent["type"], connectorId: ConnectorId, correlationId: string, attempt: number): void {
    this.publish({ type, connectorId, correlationId, occurredAt: new Date().toISOString(), attempt });
  }
}
