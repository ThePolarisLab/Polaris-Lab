# ADR-001: Start Polaris as a Modular Monolith

- **Status:** Accepted
- **Date:** 2026-07-13

## Context

Polaris has a conceptual service architecture, but the initial team and product scope do not justify distributed deployment complexity.

## Decision

Polaris v0.1 will be implemented as a modular monolith.

Each capability will retain explicit boundaries through packages, repository interfaces, schemas, and application services. Extraction into independently deployed services will occur only when operational evidence justifies it.

## Consequences

### Positive

- faster iteration
- simpler local development
- easier testing and debugging
- one deployment unit
- lower operational overhead

### Trade-offs

- stronger discipline is required to preserve module boundaries
- scaling remains shared until a module is extracted
