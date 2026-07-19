import { CreateRelationshipInput, UpdateRelationshipInput } from "./Relationship";
import { RELATIONSHIP_TYPES } from "./RelationshipTypes";

const assertNonEmpty = (value: string, field: string): void => {
  if (!value.trim()) throw new Error(`${field} is required`);
};

const assertConfidence = (value: number): void => {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    throw new Error("confidence must be between 0 and 1");
  }
};

export class RelationshipValidator {
  static validateCreate(input: CreateRelationshipInput): void {
    assertNonEmpty(input.sourceEntityId, "sourceEntityId");
    assertNonEmpty(input.targetEntityId, "targetEntityId");

    if (input.sourceEntityId === input.targetEntityId) {
      throw new Error("self relationships are not allowed");
    }

    if (!RELATIONSHIP_TYPES.includes(input.type)) {
      throw new Error(`unsupported relationship type: ${input.type}`);
    }

    if (input.confidence !== undefined) assertConfidence(input.confidence);
  }

  static validateUpdate(input: UpdateRelationshipInput): void {
    if (input.type !== undefined && !RELATIONSHIP_TYPES.includes(input.type)) {
      throw new Error(`unsupported relationship type: ${input.type}`);
    }
    if (input.confidence !== undefined) assertConfidence(input.confidence);
  }
}
