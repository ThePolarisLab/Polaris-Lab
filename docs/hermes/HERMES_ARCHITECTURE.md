# Hermes Reference Architecture

## Architectural intent

Hermes is a provider-neutral integration and intelligence layer built on Polaris Runtime. It separates external-system access from enterprise meaning and separates intelligence from material action.

## Logical flow

```text
External System
  -> Connector Adapter
  -> Connector Runtime Contract
  -> Evidence Envelope
  -> Canonical Ingestion Event
  -> Normalization and Correlation
  -> Enterprise Record Store / Read Models
  -> Executive Briefing and Athena Reasoning
  -> Proposed Action
  -> Human Approval Boundary
  -> Authorized Execution Adapter
```

## Core components

### 1. Connector contracts

Provider-neutral interfaces define connector identity, declared capabilities, health, synchronization requests, checkpoints, and results. Vendor adapters implement these contracts without entering the domain core.

### 2. Connector runtime

The Runtime schedules synchronization workers, publishes lifecycle events, records metrics, evaluates health, and exposes Mission Control snapshots. Hermes must reuse these existing boundaries rather than duplicate them.

### 3. Evidence envelope

Every observation entering Hermes must retain:

- organization and tenant identity;
- source system and connector identity;
- source record identity;
- observation and ingestion timestamps;
- correlation and causation identifiers;
- schema version;
- idempotency key;
- integrity metadata where available;
- original evidence reference;
- normalized payload.

### 4. Canonical ingestion events

Connectors emit versioned events such as:

- `hermes.connector.sync.requested.v1`;
- `hermes.connector.sync.started.v1`;
- `hermes.evidence.observed.v1`;
- `hermes.record.normalized.v1`;
- `hermes.connector.sync.completed.v1`;
- `hermes.connector.sync.failed.v1`.

Events must comply with the Polaris canonical event standard and must not expose raw secrets.

### 5. Normalization boundary

Normalization maps vendor records into stable enterprise concepts. Initial concept families include:

- message and conversation;
- customer and counterparty;
- load and shipment;
- vehicle, trailer, driver, and location;
- invoice, payment, expense, and fuel transaction;
- maintenance event and asset condition;
- document, commitment, alert, and decision.

Source evidence remains available so normalized records never erase provenance.

### 6. Correlation and read models

Correlation links records only within an authorized tenant boundary. Read models serve executive use cases without making operational systems depend on Athena or a user interface.

### 7. Executive intelligence

Briefs and recommendations must include evidence references, confidence or uncertainty, material assumptions, and relevant freshness. Intelligence may propose actions but cannot silently execute material actions.

### 8. Approval and execution boundary

Material operations require an explicit approval contract recording:

- proposed action;
- evidence and rationale;
- affected tenant and systems;
- expected consequences;
- approving identity;
- approval time and scope;
- execution result and audit evidence.

## Dependency rules

- Domain contracts do not import vendor SDKs.
- Connector adapters depend inward on contracts; contracts never depend on adapters.
- Runtime remains independent of Hermes business semantics.
- Athena consumes read models and evidence; ingestion does not depend on Athena.
- User interfaces consume APIs/read models and do not own business rules.
- Secrets are referenced through secure providers and are never placed in events, logs, or domain records.

## Reliability requirements

- idempotent ingestion;
- checkpointed synchronization;
- bounded retry policies;
- cancellation and timeout support;
- partial-failure reporting;
- rate-limit awareness;
- replay-safe canonical events;
- immutable audit evidence;
- metrics and health integration;
- deterministic tests through injected clocks and adapters.

## Security requirements

- explicit organization and tenant scope;
- least-privilege connector capabilities;
- credential references rather than plaintext credentials;
- encrypted transport and provider-backed secret storage in production;
- data minimization and retention controls;
- deny-by-default authorization;
- audited human approval for material actions;
- no cross-tenant correlation without explicit authority.

## Initial implementation boundary

The first implementation milestone will create only the provider-neutral connector foundation: contracts, capability declarations, evidence-envelope types, synchronization result types, validation, tests, and documentation. It will not yet connect a live vendor.