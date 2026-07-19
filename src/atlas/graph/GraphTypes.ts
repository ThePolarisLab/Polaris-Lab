import { AtlasEntity } from "../entity";
import { AtlasRelationship, RelationshipType } from "../relationship";

export type GraphDirection = "outgoing" | "incoming" | "both";

export interface NeighborQuery {
  direction?: GraphDirection;
  relationshipTypes?: RelationshipType[];
}

export interface GraphNeighbor {
  entity: AtlasEntity;
  relationship: AtlasRelationship;
  direction: Exclude<GraphDirection, "both">;
}

export interface GraphSnapshot {
  entities: AtlasEntity[];
  relationships: AtlasRelationship[];
}
