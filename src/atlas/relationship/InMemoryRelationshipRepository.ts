import { AtlasRelationship, RelationshipQuery, UpdateRelationshipInput } from "./Relationship";
import { RelationshipRepository } from "./RelationshipRepository";
import { RelationshipValidator } from "./RelationshipValidator";

const clone = (value: AtlasRelationship): AtlasRelationship => ({
  ...value,
  metadata: structuredClone(value.metadata),
  createdAt: new Date(value.createdAt),
  updatedAt: new Date(value.updatedAt),
});

export class InMemoryRelationshipRepository implements RelationshipRepository {
  private readonly relationships = new Map<string, AtlasRelationship>();

  async save(relationship: AtlasRelationship): Promise<AtlasRelationship> {
    if (this.relationships.has(relationship.id)) throw new Error(`relationship already exists: ${relationship.id}`);
    this.relationships.set(relationship.id, clone(relationship));
    return clone(relationship);
  }

  async getById(id: string): Promise<AtlasRelationship | undefined> {
    const relationship = this.relationships.get(id);
    return relationship ? clone(relationship) : undefined;
  }

  async list(query: RelationshipQuery = {}): Promise<AtlasRelationship[]> {
    return [...this.relationships.values()]
      .filter((relationship) => !query.sourceEntityId || relationship.sourceEntityId === query.sourceEntityId)
      .filter((relationship) => !query.targetEntityId || relationship.targetEntityId === query.targetEntityId)
      .filter((relationship) => !query.types || query.types.includes(relationship.type))
      .filter((relationship) => !query.status || relationship.status === query.status)
      .map(clone);
  }

  async update(id: string, input: UpdateRelationshipInput): Promise<AtlasRelationship> {
    RelationshipValidator.validateUpdate(input);
    const current = this.relationships.get(id);
    if (!current) throw new Error(`relationship not found: ${id}`);

    const updated: AtlasRelationship = {
      ...current,
      type: input.type ?? current.type,
      metadata: input.metadata === undefined ? structuredClone(current.metadata) : structuredClone(input.metadata),
      confidence: input.confidence ?? current.confidence,
      status: input.status ?? current.status,
      version: current.version + 1,
      updatedAt: input.now ? new Date(input.now) : new Date(),
    };
    this.relationships.set(id, clone(updated));
    return clone(updated);
  }

  async delete(id: string): Promise<boolean> {
    return this.relationships.delete(id);
  }
}
