import { AtlasEntity } from "../entity";
import { AtlasRelationship, RelationshipType } from "../relationship";
import { GraphDirection } from "../graph";

export interface GraphQueryOptions {
  maxDepth?: number;
  direction?: GraphDirection;
  relationshipTypes?: RelationshipType[];
}

export interface GraphPathStep {
  from: AtlasEntity;
  relationship: AtlasRelationship;
  to: AtlasEntity;
  direction: Exclude<GraphDirection, "both">;
}

export interface GraphPath {
  start: AtlasEntity;
  end: AtlasEntity;
  steps: GraphPathStep[];
  depth: number;
}

export interface TraversalNode {
  entity: AtlasEntity;
  depth: number;
  path: GraphPathStep[];
}

export interface TraversalResult {
  start: AtlasEntity;
  nodes: TraversalNode[];
  visitedEntityIds: string[];
  maxDepth: number;
}
