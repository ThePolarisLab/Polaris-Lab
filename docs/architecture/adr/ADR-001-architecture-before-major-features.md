# ADR-001 — Architecture Before Major Features

**Status:** Accepted  
**Date:** 2026-07-17  
**Decision owner:** The Builder

## Context

Polaris has grown from an initial Chief of Staff prototype into a full-stack application containing multiple business, intelligence, persistence, presentation, and engineering capabilities. PGE-002 Repository Intelligence will expand the GitHub Engine substantially and will depend on a correct understanding of the existing repository.

Continuing to add major capabilities without an explicit architecture baseline creates risk of duplicated modules, unclear ownership, inconsistent APIs, and undocumented coupling.

## Decision

Before beginning a major feature, Polaris Engineering will:

1. inspect the relevant current repository structure and behavior;
2. identify the owning domain and architectural layer;
3. document affected interfaces, dependencies, data, security boundaries, and tests;
4. obtain Builder approval for the proposed placement and scope;
5. implement through a feature branch and pull request.

Architecture documents must distinguish verified current state from proposed target state.

## Consequences

### Positive

- Major features receive a clear architectural home.
- Repository evidence replaces assumptions and memory.
- Change-impact analysis becomes easier.
- Documentation and code evolve together.
- Future contributors and AI agents can understand why decisions were made.

### Costs

- Major features require a small design and discovery investment before implementation.
- Architecture documentation must be maintained.
- Some urgent work may need an explicitly documented exception.

## Application to PGE-002

Repository Intelligence will extend the established GitHub Engine boundary under `chief-of-staff/backend/app/github_engine/`. Its final interface will be designed after ARC-001 completes the relevant API, dependency, and test inventory.

## Guardrail

This decision is intended to prevent unstructured growth, not to introduce heavy bureaucracy. Small, reversible fixes may use a lightweight assessment proportional to their risk.
