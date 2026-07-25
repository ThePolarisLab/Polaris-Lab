import {
  AnyExecutiveEntity,
  BusinessEvent,
  ExecutiveEntityKind,
  assertValidExecutiveEntity,
} from "./contracts";

export interface ExecutiveRepository {
  upsert(entity: AnyExecutiveEntity): Promise<void>;
  getById<T extends AnyExecutiveEntity = AnyExecutiveEntity>(id: string): Promise<T | undefined>;
  listByKind<T extends AnyExecutiveEntity = AnyExecutiveEntity>(kind: ExecutiveEntityKind): Promise<readonly T[]>;
  appendEvent(event: BusinessEvent): Promise<void>;
  listEvents(organizationId: string): Promise<readonly BusinessEvent[]>;
}

export class InMemoryExecutiveRepository implements ExecutiveRepository {
  private readonly entities = new Map<string, AnyExecutiveEntity>();
  private readonly events: BusinessEvent[] = [];

  async upsert(entity: AnyExecutiveEntity): Promise<void> {
    assertValidExecutiveEntity(entity);
    const existing = this.entities.get(entity.id);
    if (existing && existing.organizationId !== entity.organizationId) {
      throw new Error("Cross-organization executive entity update denied");
    }
    if (existing && entity.version <= existing.version) {
      throw new Error("Executive entity version must increase");
    }
    this.entities.set(entity.id, freezeEntity(entity));
  }

  async getById<T extends AnyExecutiveEntity = AnyExecutiveEntity>(id: string): Promise<T | undefined> {
    return this.entities.get(id) as T | undefined;
  }

  async listByKind<T extends AnyExecutiveEntity = AnyExecutiveEntity>(kind: ExecutiveEntityKind): Promise<readonly T[]> {
    return Object.freeze(
      [...this.entities.values()].filter((entity) => entity.kind === kind) as T[],
    );
  }

  async appendEvent(event: BusinessEvent): Promise<void> {
    if (!event.id.trim() || !event.organizationId.trim() || !event.type.trim()) {
      throw new Error("Business event id, organization id, and type are required");
    }
    if (this.events.some((candidate) => candidate.id === event.id)) return;
    this.events.push(Object.freeze({ ...event, evidence: Object.freeze([...event.evidence]) }));
  }

  async listEvents(organizationId: string): Promise<readonly BusinessEvent[]> {
    return Object.freeze(this.events.filter((event) => event.organizationId === organizationId));
  }
}

function freezeEntity<T extends AnyExecutiveEntity>(entity: T): T {
  return Object.freeze({
    ...entity,
    externalReferences: Object.freeze([...entity.externalReferences]),
    evidence: Object.freeze([...entity.evidence]),
    metadata: Object.freeze({ ...entity.metadata }),
  }) as T;
}
