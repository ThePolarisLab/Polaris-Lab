# ADR-009 — Hermes Uses Provider-Neutral Connector Contracts

## Status

Proposed.

## Context

Hermes must integrate Microsoft 365, Motive, QuickBooks Online, dispatch systems, fuel providers, maintenance platforms, and future sources. Directly embedding vendor SDKs and schemas into the Polaris domain would create coupling, weaken testability, complicate tenant security, and make replacement or parallel providers expensive.

## Decision

Hermes will define provider-neutral connector contracts in its domain-facing layer. Vendor implementations will be adapters at the system boundary.

A connector must declare:

- stable connector identity and version;
- provider and capability metadata;
- organization and tenant scope;
- supported synchronization modes;
- credential reference requirements;
- health and readiness state;
- checkpoint and idempotency behavior;
- synchronization input and structured result;
- evidence envelopes for observed records.

Vendor SDK objects, access tokens, refresh tokens, and raw secret values must not cross into canonical events or normalized enterprise records.

## Consequences

### Positive

- vendor replacement and multi-provider support;
- deterministic adapter testing;
- stronger secret and tenant boundaries;
- stable enterprise models;
- reusable Runtime scheduling, health, and observability;
- clearer provenance and audit trails.

### Costs

- additional mapping code;
- deliberate capability negotiation;
- schema-version governance;
- potential loss of vendor-specific detail unless preserved in evidence references or extension fields.

## Alternatives rejected

### One integration service per vendor with no shared contract

Rejected because lifecycle, security, observability, and evidence semantics would diverge.

### Canonical model mirrors the first vendor

Rejected because it would make vendor assumptions permanent and violate architecture-over-convenience.

### Connectors write directly into executive read models

Rejected because it would bypass canonical evidence, normalization, idempotency, and audit boundaries.

## Guardrails

- adapters may use vendor SDKs internally;
- domain contracts must remain vendor-neutral;
- extension data must be namespaced and evidence-linked;
- all connector activity is tenant-scoped;
- material actions require a separate approval and execution contract;
- this ADR must be revisited if a concrete use case cannot be represented without unacceptable information loss.