import { randomUUID } from "crypto";
import { AtlasRelationship, CreateRelationshipInput } from "./Relationship";
import { RelationshipValidator } from "./RelationshipValidator";

const cloneMetadata = (metadata: Record<string, unknown> = {}): Record<string, unknown> =>
  structuredClone(metadata);

export class RelationshipFactory {
  static create(input: CreateRelationshipInput): AtlasRelationship {
    RelationshipValidator.validateCreate(input);
    const now = input.now ? new Date(input.now) : new Date();

    return {
      id: input.id?.trim() || randomUUID(),
      sourceEntityId: input.sourceEntityId.trim(),
      targetEntityId: input.targetEntityId.trim(),
      type: input.type,
      metadata: cloneMetadata(input.metadata),
      confidence: input.confidence ?? 1,
      status: input.status ?? "active",
      version: 1,
      createdAt: now,
      updatedAt: now,
    };
  }
}
