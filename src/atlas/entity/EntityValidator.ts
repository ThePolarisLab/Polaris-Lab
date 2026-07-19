import { CreateEntityInput, UpdateEntityInput } from "./Entity";
import { isEntityType } from "./EntityTypes";

export class EntityValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EntityValidationError";
  }
}

export class EntityValidator {
  static validateCreate(input: CreateEntityInput): void {
    if (!isEntityType(input.type)) {
      throw new EntityValidationError(`Unsupported entity type: ${String(input.type)}`);
    }

    if (!input.name || input.name.trim().length === 0) {
      throw new EntityValidationError("Entity name is required");
    }

    if (input.id !== undefined && input.id.trim().length === 0) {
      throw new EntityValidationError("Entity id cannot be empty");
    }

    this.validateTags(input.tags);
    this.validateMetadata(input.metadata);
  }

  static validateUpdate(input: UpdateEntityInput): void {
    if (input.name !== undefined && input.name.trim().length === 0) {
      throw new EntityValidationError("Entity name cannot be empty");
    }

    this.validateTags(input.tags);
    this.validateMetadata(input.metadata);
  }

  private static validateTags(tags?: string[]): void {
    if (!tags) return;
    if (tags.some((tag) => tag.trim().length === 0)) {
      throw new EntityValidationError("Entity tags cannot contain empty values");
    }
  }

  private static validateMetadata(metadata?: Record<string, unknown>): void {
    if (!metadata) return;
    if (Object.keys(metadata).some((key) => key.trim().length === 0)) {
      throw new EntityValidationError("Entity metadata keys cannot be empty");
    }
  }
}
