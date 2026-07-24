import { ConnectorCheckpoint, ConnectorId, ConnectorScope } from "../connectors/contracts";

export interface CheckpointStore {
  load(connectorId: ConnectorId, scope: ConnectorScope): Promise<ConnectorCheckpoint | undefined>;
  save(connectorId: ConnectorId, scope: ConnectorScope, checkpoint: ConnectorCheckpoint): Promise<void>;
}

const keyOf = (connectorId: ConnectorId, scope: ConnectorScope): string =>
  `${scope.organizationId}:${scope.tenantId}:${connectorId}`;

export class InMemoryCheckpointStore implements CheckpointStore {
  private readonly checkpoints = new Map<string, ConnectorCheckpoint>();

  public async load(connectorId: ConnectorId, scope: ConnectorScope): Promise<ConnectorCheckpoint | undefined> {
    return this.checkpoints.get(keyOf(connectorId, scope));
  }

  public async save(connectorId: ConnectorId, scope: ConnectorScope, checkpoint: ConnectorCheckpoint): Promise<void> {
    this.checkpoints.set(keyOf(connectorId, scope), checkpoint);
  }
}
