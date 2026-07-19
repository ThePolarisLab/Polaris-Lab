import { EntityStatus, EntityType } from "./EntityTypes";

export interface AtlasEntity {
  id: string;
  type: EntityType;
  name: string;
  description?: string;
  metadata: Record<string, unknown>;
  tags: string[];
  status: EntityStatus;
  version: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface CreateEntityInput {
  id?: string;
  type: EntityType;
  name: string;
  description?: string;
  metadata?: Record<string, unknown>;
  tags?: string[];
  status?: EntityStatus;
  now?: Date;
}

export interface UpdateEntityInput {
  name?: string;
  description?: string;
  metadata?: Record<string, unknown>;
  tags?: string[];
  status?: EntityStatus;
  now?: Date;
}
