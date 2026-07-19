export const ENTITY_TYPES = [
  "project",
  "repository",
  "document",
  "adr",
  "task",
  "decision",
  "person",
  "organization",
  "component",
  "workflow",
  "release",
  "issue",
] as const;

export type EntityType = (typeof ENTITY_TYPES)[number];

export type EntityStatus = "active" | "inactive" | "archived";

export function isEntityType(value: string): value is EntityType {
  return (ENTITY_TYPES as readonly string[]).includes(value);
}
