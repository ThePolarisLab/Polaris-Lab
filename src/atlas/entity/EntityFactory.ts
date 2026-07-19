import { randomUUID } from "node:crypto";
import { AtlasEntity, CreateEntityInput, UpdateEntityInput } from "./Entity";
import { EntityValidator } from "./EntityValidator";

function uniqueTags(tags: string[] = []): string[] {
  return [...new Set(tags.map((tag) => tag.trim()))];
}

function cloneMetadata(metadata: Record<string, unknown> = {}): Record<string, unknown> {
  return { ...metadata };
}

export class EntityFactory {
  static create(input: CreateEntityInput): AtlasEntity {
    EntityValidator.validateCreate(input);
    const now = new Date(input.now ?? new Date());

    return {
      id: input.id ?? randomUUID(),
      type: input.type,
      name: input.name.trim(),
      description: input.description?.trim(),
      metadata: cloneMetadata(input.metadata),
      tags: uniqueTags(input.tags),
      status: input.status ?? "active",
      version: 1,
      createdAt: now,
      updatedAt: now,
    };
  }

  static update(entity: AtlasEntity, input: UpdateEntityInput): AtlasEntity {
    EntityValidator.validateUpdate(input);
    const now = new Date(input.now ?? new Date());

    return {
      ...entity,
      name: input.name?.trim() ?? entity.name,
      description:
        input.description === undefined ? entity.description : input.description.trim(),
      metadata:
        input.metadata === undefined ? cloneMetadata(entity.metadata) : cloneMetadata(input.metadata),
      tags: input.tags === undefined ? [...entity.tags] : uniqueTags(input.tags),
      status: input.status ?? entity.status,
      version: entity.version + 1,
      createdAt: new Date(entity.createdAt),
      updatedAt: now,
    };
  }
}
