import {
  ConnectorContext,
  ConnectorDescriptor,
  ConnectorHealthReport,
  ConnectorHealthStatus,
  ConnectorState,
  IConnector,
  SynchronizationRequest,
  SynchronizationResult,
} from "./contracts";
import {
  assertSameScope,
  ConnectorContractError,
  validateDescriptor,
  validateSynchronizationRequest,
} from "./validation";

export abstract class AbstractConnector<TPayload = unknown> implements IConnector<TPayload> {
  private currentState = ConnectorState.Ready;

  protected constructor(public readonly descriptor: ConnectorDescriptor) {
    validateDescriptor(descriptor);
  }

  public get state(): ConnectorState {
    return this.currentState;
  }

  public async connect(context: ConnectorContext): Promise<void> {
    assertSameScope(this.descriptor.scope, context.scope);
    this.assertState([ConnectorState.Ready, ConnectorState.Disconnected, ConnectorState.Degraded]);
    this.currentState = ConnectorState.Authenticating;

    try {
      await this.onConnect(context);
      this.currentState = ConnectorState.Connected;
    } catch (error) {
      this.currentState = ConnectorState.Failed;
      throw error;
    }
  }

  public async synchronize(
    request: SynchronizationRequest,
  ): Promise<SynchronizationResult<TPayload>> {
    validateSynchronizationRequest(request);
    assertSameScope(this.descriptor.scope, request.scope);
    this.assertState([ConnectorState.Connected, ConnectorState.Degraded]);
    this.currentState = ConnectorState.Synchronizing;

    try {
      const result = await this.onSynchronize(request);
      this.currentState = result.failures.length > 0 ? ConnectorState.Degraded : ConnectorState.Connected;
      return result;
    } catch (error) {
      this.currentState = ConnectorState.Failed;
      throw error;
    }
  }

  public async health(context: ConnectorContext): Promise<ConnectorHealthReport> {
    assertSameScope(this.descriptor.scope, context.scope);
    const report = await this.onHealth(context);
    assertSameScope(this.descriptor.scope, report.scope);

    if (report.connectorId !== this.descriptor.identity.id) {
      throw new ConnectorContractError(
        "HERMES_CONNECTOR_ID_MISMATCH",
        "Health report connector id does not match descriptor",
      );
    }

    return report;
  }

  public async disconnect(context: ConnectorContext): Promise<void> {
    assertSameScope(this.descriptor.scope, context.scope);

    if (this.currentState === ConnectorState.Disconnected) {
      return;
    }

    await this.onDisconnect(context);
    this.currentState = ConnectorState.Disconnected;
  }

  protected abstract onConnect(context: ConnectorContext): Promise<void>;

  protected abstract onSynchronize(
    request: SynchronizationRequest,
  ): Promise<SynchronizationResult<TPayload>>;

  protected async onHealth(context: ConnectorContext): Promise<ConnectorHealthReport> {
    const healthyStates = [ConnectorState.Connected, ConnectorState.Synchronizing];
    return {
      connectorId: this.descriptor.identity.id,
      scope: context.scope,
      status: healthyStates.includes(this.currentState)
        ? ConnectorHealthStatus.Healthy
        : this.currentState === ConnectorState.Degraded
          ? ConnectorHealthStatus.Degraded
          : ConnectorHealthStatus.Unhealthy,
      state: this.currentState,
      checkedAt: new Date().toISOString(),
    };
  }

  protected abstract onDisconnect(context: ConnectorContext): Promise<void>;

  private assertState(allowed: readonly ConnectorState[]): void {
    if (!allowed.includes(this.currentState)) {
      throw new ConnectorContractError(
        "HERMES_INVALID_CONNECTOR_STATE",
        `Connector cannot perform this operation while ${this.currentState}`,
        { state: this.currentState, allowed },
      );
    }
  }
}
