import { ConnectorCapability, ConnectorId, IConnector } from "../connectors/contracts";

export class ConnectorRegistry {
  private readonly connectors = new Map<ConnectorId, IConnector>();

  public register(connector: IConnector): void {
    const id = connector.descriptor.identity.id;
    if (this.connectors.has(id)) throw new Error(`Connector already registered: ${id}`);
    this.connectors.set(id, connector);
  }

  public unregister(id: ConnectorId): boolean { return this.connectors.delete(id); }

  public get(id: ConnectorId): IConnector {
    const connector = this.connectors.get(id);
    if (!connector) throw new Error(`Connector not registered: ${id}`);
    return connector;
  }

  public list(): readonly IConnector[] { return [...this.connectors.values()]; }

  public findByCapability(capability: ConnectorCapability): readonly IConnector[] {
    return this.list().filter((connector) => connector.descriptor.capabilities.includes(capability));
  }
}
