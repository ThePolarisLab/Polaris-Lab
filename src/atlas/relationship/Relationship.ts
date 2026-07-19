import { RelationshipStatus, RelationshipType } from "./RelationshipTypes";

export interface AtlasRelationship {
  id: string;
  sourceEntityId: string;
  targetEntityId: string;
  type: RelationshipType;
  metadata: Record<string, unknown>;
  confidence: number;
  status: RelationshipStatus;
  version: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface CreateRelationshipInput {
  id?: string;
  sourceEntityId: string;
  targetEntityId: string;
  type: RelationshipType;
  metadata?: Record<string, unknown>;
  confidence?: number;
  status?: RelationshipStatus;
  now?: Date;
}

export interface UpdateRelationshipInput {
  type?: RelationshipType;
  metadata?: Record<string, unknown>;
  confidence?: number;
  status?: RelationshipStatus;
  now?: Date;
}

export interface RelationshipQuery {
  sourceEntityId?: string;
  targetEntityId?: string;
  types?: RelationshipType[];
  status?: RelationshipStatus;
}
