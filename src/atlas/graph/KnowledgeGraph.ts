import { AtlasEntity, CreateEntityInput, EntityFactory, EntityRepository } from "../entity";
import {
  AtlasRelationship,
  CreateRelationshipInput,
  RelationshipFactory,
  RelationshipRepository,
} from "../relationship";
import { GraphNeighbor, GraphSnapshot, NeighborQuery } from "./GraphTypes";

const normalizeId = (id: string): string => id.trim();

export class KnowledgeGraph {
  constructor(
    private readonly entities: EntityRepository,
    private readonly relationships: RelationshipRepository,
  ) {}

  async addEntity(input: CreateEntityInput): Promise<AtlasEntity> {
    const entity = EntityFactory.create(input);
    return this.entities.save(entity);
  }

  async addRelationship(input: CreateRelationshipInput): Promise<AtlasRelationship> {
    const sourceId = normalizeId(input.sourceEntityId);
    const targetId = normalizeId(input.targetEntityId);
    const [source, target] = await Promise.all([
      this.entities.findById(sourceId),
      this.entities.findById(targetId),
    ]);

    if (!source) {
      throw new Error(`Source entity not found: ${sourceId}`);
    }
    if (!target) {
      throw new Error(`Target entity not found: ${targetId}`);
    }

    return this.relationships.save(
      RelationshipFactory.create({
        ...input,
        sourceEntityId: sourceId,
        targetEntityId: targetId,
      }),
    );
  }

  async getEntity(id: string): Promise<AtlasEntity | undefined> {
    return this.entities.findById(normalizeId(id));
  }

  async getRelationship(id: string): Promise<AtlasRelationship | undefined> {
    return this.relationships.getById(normalizeId(id));
  }

  async neighbors(entityId: string, query: NeighborQuery = {}): Promise<GraphNeighbor[]> {
    const id = normalizeId(entityId);
    const entity = await this.entities.findById(id);
    if (!entity) {
      throw new Error(`Entity not found: ${id}`);
    }

    const direction = query.direction ?? "both";
    const allowedTypes = query.relationshipTypes;
    const matches = await this.relationships.list();
    const neighbors: GraphNeighbor[] = [];

    for (const relationship of matches) {
      if (allowedTypes && !allowedTypes.includes(relationship.type)) {
        continue;
      }

      if ((direction === "outgoing" || direction === "both") && relationship.sourceEntityId === id) {
        const target = await this.entities.findById(relationship.targetEntityId);
        if (target) {
          neighbors.push({ entity: target, relationship, direction: "outgoing" });
        }
      }

      if ((direction === "incoming" || direction === "both") && relationship.targetEntityId === id) {
        const source = await this.entities.findById(relationship.sourceEntityId);
        if (source) {
          neighbors.push({ entity: source, relationship, direction: "incoming" });
        }
      }
    }

    return neighbors;
  }

  async relationshipsBetween(sourceEntityId: string, targetEntityId: string): Promise<AtlasRelationship[]> {
    return this.relationships.list({
      sourceEntityId: normalizeId(sourceEntityId),
      targetEntityId: normalizeId(targetEntityId),
    });
  }

  async removeRelationship(id: string): Promise<boolean> {
    return this.relationships.delete(normalizeId(id));
  }

  async removeEntity(id: string): Promise<boolean> {
    const normalizedId = normalizeId(id);
    const incident = await this.relationships.list();
    const hasRelationships = incident.some(
      (relationship) =>
        relationship.sourceEntityId === normalizedId || relationship.targetEntityId === normalizedId,
    );

    if (hasRelationships) {
      throw new Error(`Cannot delete entity with relationships: ${normalizedId}`);
    }

    return this.entities.delete(normalizedId);
  }

  async snapshot(): Promise<GraphSnapshot> {
    const [entities, relationships] = await Promise.all([
      this.entities.list(),
      this.relationships.list(),
    ]);
    return { entities, relationships };
  }
}
