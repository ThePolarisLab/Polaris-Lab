import { AtlasEntity, UpdateEntityInput } from "./Entity";
import { EntityFactory } from "./EntityFactory";
import { EntityRepository } from "./EntityRepository";
import { EntityType } from "./EntityTypes";

function cloneEntity(entity: AtlasEntity): AtlasEntity {
  return {
    ...entity,
    metadata: { ...entity.metadata },
    tags: [...entity.tags],
    createdAt: new Date(entity.createdAt),
    updatedAt: new Date(entity.updatedAt),
  };
}

export class InMemoryEntityRepository implements EntityRepository {
  private readonly entities = new Map<string, AtlasEntity>();

  async save(entity: AtlasEntity): Promise<AtlasEntity> {
    if (this.entities.has(entity.id)) {
      throw new Error(`Entity already exists: ${entity.id}`);
    }
    this.entities.set(entity.id, cloneEntity(entity));
    return cloneEntity(entity);
  }

  async findById(id: string): Promise<AtlasEntity | undefined> {
    const entity = this.entities.get(id);
    return entity ? cloneEntity(entity) : undefined;
  }

  async findByType(type: EntityType): Promise<AtlasEntity[]> {
    return [...this.entities.values()]
      .filter((entity) => entity.type === type)
      .map(cloneEntity);
  }

  async list(): Promise<AtlasEntity[]> {
    return [...this.entities.values()].map(cloneEntity);
  }

  async update(id: string, input: UpdateEntityInput): Promise<AtlasEntity> {
    const current = this.entities.get(id);
    if (!current) {
      throw new Error(`Entity not found: ${id}`);
    }
    const updated = EntityFactory.update(current, input);
    this.entities.set(id, cloneEntity(updated));
    return cloneEntity(updated);
  }

  async delete(id: string): Promise<boolean> {
    return this.entities.delete(id);
  }
}
