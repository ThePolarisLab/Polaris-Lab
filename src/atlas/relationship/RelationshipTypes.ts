export const RELATIONSHIP_TYPES = [
  "owns",
  "manages",
  "depends_on",
  "contains",
  "references",
  "created_by",
  "reports_to",
  "part_of",
  "implements",
  "documents",
  "approved_by",
  "supersedes",
] as const;

export type RelationshipType = (typeof RELATIONSHIP_TYPES)[number];

export type RelationshipStatus = "active" | "inactive" | "archived";
