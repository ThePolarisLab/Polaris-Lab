import { AtlasEntity, UpdateEntityInput } from "./Entity";
import { EntityType } from "./EntityTypes";

export interface EntityRepository {
  save(entity: AtlasEntity): Promise<AtlasEntity>;
  findById(id: string): Promise<AtlasEntity | undefined>;
  findByType(type: EntityType): Promise<AtlasEntity[]>;
  list(): Promise<AtlasEntity[]>;
  update(id: string, input: UpdateEntityInput): Promise<AtlasEntity>;
  delete(id: string): Promise<boolean>;
}
