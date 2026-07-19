import { AthenaDecision, AthenaIntent, AthenaRequest } from "../types";

export type MemoryKind =
  | "decision"
  | "conversation"
  | "project"
  | "organization"
  | "fact"
  | "task"
  | "meeting";

export interface MemoryScope {
  userId: string;
  project?: string;
  organization?: string;
}

export interface MemoryRecord {
  id: string;
  kind: MemoryKind;
  scope: MemoryScope;
  title: string;
  content: string;
  intent?: AthenaIntent;
  tags: string[];
  sourceRequestId?: string;
  createdAt: Date;
  updatedAt: Date;
  importance: number;
  metadata?: Record<string, unknown>;
}

export interface MemoryQuery {
  userId: string;
  text?: string;
  kinds?: MemoryKind[];
  project?: string;
  organization?: string;
  tags?: string[];
  limit?: number;
  now?: Date;
}

export interface MemoryUpdateInput {
  userId: string;
  title?: string;
  content?: string;
  tags?: string[];
  importance?: number;
  metadata?: Record<string, unknown>;
  now?: Date;
}

export interface MemoryMatch {
  record: MemoryRecord;
  relevance: number;
  recency: number;
  importance: number;
  score: number;
}

export interface ExecutiveMemorySnapshot {
  matches: MemoryMatch[];
  query: MemoryQuery;
}

export interface DecisionMemoryInput {
  request: AthenaRequest;
  decision: AthenaDecision;
}
