import { AtlasEntity } from "../entity";
import { AtlasRelationship } from "../relationship";
import { GraphPath } from "../query";

export interface ExplanationEvidence {
  entityId: string;
  entityName: string;
  relationshipId?: string;
  relationshipType?: AtlasRelationship["type"];
  confidence: number;
}

export interface ExplanationStep {
  position: number;
  statement: string;
  from: AtlasEntity;
  to: AtlasEntity;
  relationship: AtlasRelationship;
  confidence: number;
}

export interface GraphExplanation {
  summary: string;
  narrative: string;
  start: AtlasEntity;
  end: AtlasEntity;
  path: GraphPath;
  steps: ExplanationStep[];
  evidence: ExplanationEvidence[];
  confidence: number;
}

export interface ExplainPathOptions {
  includeEntityTypes?: boolean;
  includeEvidenceIds?: boolean;
}
