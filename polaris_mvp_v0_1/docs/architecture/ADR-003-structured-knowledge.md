# ADR-003: Introduce Structured Knowledge Objects

- **Status:** Accepted
- **Date:** 2026-07-14

## Decision

Polaris will distinguish enduring knowledge from raw memory through versioned Knowledge Objects.

Knowledge Objects carry classification, authorship, importance, confidence, truth status, visibility, provenance, and optional links to source memories.

Relationships are first-class records with their own evidence and confidence.

## Consequences

- Foundation principles can be treated differently from operational notes.
- Existing memories remain preserved and can be migrated idempotently.
- Future reasoning can trace conclusions to explicit knowledge and relationships.
