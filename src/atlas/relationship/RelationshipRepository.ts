import { AtlasRelationship, RelationshipQuery, UpdateRelationshipInput } from "./Relationship";

export interface RelationshipRepository {
  save(relationship: AtlasRelationship): Promise<AtlasRelationship>;
  getById(id: string): Promise<AtlasRelationship | undefined>;
  list(query?: RelationshipQuery): Promise<AtlasRelationship[]>;
  update(id: string, input: UpdateRelationshipInput): Promise<AtlasRelationship>;
  delete(id: string): Promise<boolean>;
}
