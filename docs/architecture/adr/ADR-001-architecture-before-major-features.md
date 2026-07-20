# ADR-001 — Architecture Before Major Features

**Status:** Accepted  
**Date:** 2026-07-17  
**Reviewed:** 2026-07-20  
**Decision owner:** The Builder

## Context

Polaris has evolved from an initial Chief of Staff application into a multi-domain platform spanning operational workflows, Athena orchestration, Executive Memory, Atlas knowledge capabilities, Decision Intelligence, and engineering intelligence.

Continuing to add major capabilities without an explicit architecture baseline creates risk of duplicated modules, unclear ownership, inconsistent contracts, accidental coupling, undocumented security boundaries, and incompatible persistence choices.

## Decision

Before beginning a major feature, Polaris Engineering will:

1. inspect the relevant repository structure, behavior, tests, and merged history;
2. identify the owning domain and architectural layer;
3. document affected contracts, dependencies, data, security boundaries, and runtime assumptions;
4. define verification, release, and documentation requirements;
5. obtain Builder approval for material scope and irreversible decisions;
6. implement through a feature branch and pull request;
7. update architecture documents or create an ADR when the change crosses the ADR threshold.

Architecture documents must distinguish verified current state, accepted decisions, proposed future state, and known limitations.

## Consequences

### Positive

- Major features receive a clear architectural home.
- Repository evidence replaces assumptions and memory.
- Cross-domain and cross-runtime coupling becomes explicit.
- Change-impact analysis and review become easier.
- Documentation, tests, and code evolve together.
- Future contributors and AI agents can understand why decisions were made.

### Costs

- Major features require proportionate discovery and design before implementation.
- Architecture documentation must be maintained.
- ADRs require status and supersession discipline.
- Urgent exceptions require explicit documentation rather than silent bypass.

## Application

This decision applies to all major Polaris domains, including:

- the legacy Chief of Staff application;
- Athena;
- Executive Memory;
- Atlas;
- Decision Intelligence;
- GitHub and engineering-intelligence capabilities;
- persistence, identity, security, deployment, and cross-runtime integration.

## Guardrail

This decision prevents unstructured growth; it does not require heavy bureaucracy for small, reversible, low-risk changes. The depth of architectural review should be proportional to impact, security risk, coupling, and reversibility.

## ARC-001 outcome

ARC-001 establishes the first living architecture baseline. After merge, future changes should maintain or supersede this baseline through normal documentation and ADR workflow rather than reopening ARC-001.