# Hermes v0.8 Roadmap

## Program objective

Deliver a governed, provider-neutral integration and executive-intelligence foundation on Polaris Runtime without compromising provenance, organization isolation, explainability, security, or human authority.

## Current program state

Hermes v0.8 has progressed beyond its original planning baseline. The following increments are complete and merged:

- PGE-009.1 — Hermes Charter and Architecture — PR #51.
- PGE-009.2 — Connector Contract Foundation — PR #52.
- PGE-009.3 — Connector Orchestration Runtime — PR #53.
- PGE-009.4 — Microsoft Outlook Connector — PR #54.
- PGE-009.5 — Motive Fleet Connector — PR #55.
- PGE-009.6 — QuickBooks Financial Connector — PR #56.
- PGE-009.7 — Executive Read Model — PR #57.
- PGE-009.8 — Executive Projection Engine — PR #58.
- PGE-009.9 — Executive Query Engine — PR #59.
- PGE-009.10.1 — Hermes Certification Framework — PR #65.
- PGE-009.10.2 — Reference Connector Certification — PR #67.
- PGE-009.10.3 — End-to-End Integration & Traceability — PR #69.

Athena's first deterministic reasoning milestone was merged in PR #60. Athena consumes structured evidence and executive read models; it does not bypass Hermes or call provider connectors directly.

PGE-009.10 is in progress. PGE-009.10.4 verifies checkpoint recovery, deterministic replay, failure isolation, secret redaction, and safe operational health under issue #70.

## Delivered architecture

The merged Hermes foundation includes:

- provider-neutral connector contracts;
- authentication-provider boundaries without plaintext secret ownership;
- governed connector lifecycle and capability discovery;
- checkpointed full and incremental synchronization;
- bounded retry and reconnect behavior;
- Microsoft Outlook, Motive, and QuickBooks reference connectors;
- provenance-preserving evidence envelopes and idempotency keys;
- organization-isolated executive domain entities and events;
- an idempotent Executive Projection Engine;
- provider-neutral executive query services;
- deterministic filtering, sorting, and bounded pagination;
- mandatory organization isolation and cross-domain dashboard composition;
- a governed certification manifest, integrity suite, and dedicated CI workflow;
- reference-connector contract certification;
- end-to-end provenance and replay certification.

## Delivery sequence

### PGE-009.1 — Hermes Charter and Architecture — Complete

Established the project charter, reference architecture, constitutional boundaries, provider-neutral connector ADR, and milestone plan.

### PGE-009.2 — Connector Contract Foundation — Complete

Established connector identity, organization scope, capabilities, lifecycle, health, checkpoints, synchronization, evidence, authentication, validation, provenance, schema versioning, and idempotency contracts.

### PGE-009.3 — Connector Orchestration Runtime — Complete

Added connector registration, capability discovery, synchronization orchestration, checkpoint persistence, bounded retries, recovery, and runtime lifecycle events.

### PGE-009.4 — Microsoft Outlook Connector — Complete

Added a Microsoft Graph mail boundary, mailbox discovery, full and incremental message synchronization, pagination, delta checkpoints, normalized evidence envelopes, health, and disconnect behavior. Autonomous email sending is excluded.

### PGE-009.5 — Motive Fleet Connector — Complete

Added fleet evidence synchronization for vehicles, drivers, locations, utilization, and IFTA summaries with resource-aware checkpoints, pagination, provenance, health, and lifecycle behavior.

### PGE-009.6 — QuickBooks Financial Connector — Complete

Added financial evidence synchronization for Profit and Loss, Balance Sheet, Cash Flow, accounts receivable aging, and accounts payable aging, with full and incremental synchronization, checkpoints, provenance, and idempotency. Autonomous accounting entries and payments are excluded.

### PGE-009.7 — Executive Read Model — Complete

Added provider-neutral executive contracts and storage boundaries for customers, loads, vehicles, drivers, financial snapshots, tasks, alerts, KPIs, external references, evidence references, versions, and business events.

### PGE-009.8 — Executive Projection Engine — Complete

Added deterministic, registered projections from governed evidence and business events into executive entities, including organization isolation, evidence idempotency, external-reference helpers, event ordering, and optimistic entity versions.

### PGE-009.9 — Executive Query Engine — Complete

Added typed query, filter, sort, pagination, and context contracts; repository adapters; domain query services; nested-field filtering; stable deterministic ordering; bounded pagination; mandatory organization isolation; and cross-domain dashboard composition.

### PGE-009.10 — Hermes v0.8 Integration and Certification — In progress

This increment verifies Hermes as one cohesive governed subsystem rather than as isolated components.

Completed increments:

- PGE-009.10.1 — Hermes Certification Framework — complete in PR #65.
- PGE-009.10.2 — Reference Connector Certification — complete in PR #67.
- PGE-009.10.3 — End-to-End Integration & Traceability — complete in PR #69.

Current increment:

- PGE-009.10.4 — Resilience & Security Verification — in progress under issue #70.

Planned delivery sequence:

- PGE-009.10.5 — Athena compatibility certification;
- PGE-009.10.6 — consolidated release certification.

PGE-009.10.4 deliverables:

- durable checkpoint recovery after partial failure;
- replay and duplicate-work suppression;
- connector and organization failure isolation;
- recursive secret and bearer-token redaction;
- safe connector health signals for Mission Control;
- synchronized certification evidence and documentation.

Remaining PGE-009.10 deliverables:

- compatibility verification with Athena's reasoning contracts;
- consolidated release notes and certification report.

Exit criteria:

- all required automated tests pass;
- GitHub Actions is successful;
- no unresolved critical or high-severity security findings remain;
- evidence provenance is demonstrable across the full path;
- organization isolation fails closed;
- replay and idempotency behavior is deterministic;
- Athena consumes Hermes outputs only through governed contracts;
- documentation matches the merged implementation;
- human review approves the release baseline.

## Post-certification direction

After PGE-009.10, the next program should be selected through an explicit charter and ADR review. Candidate directions include:

- authorized action proposals and human approval workflows;
- production persistence adapters;
- connector credential-vault integration;
- executive briefing composition;
- Athena–Hermes end-to-end executive insight flows;
- pilot deployment using Mor Logistics data boundaries.

None of these candidates is considered approved merely by appearing in this roadmap.

## Non-negotiable quality gates

Every increment must:

- preserve organization isolation;
- avoid plaintext secrets;
- retain source provenance;
- define idempotency and replay behavior;
- expose failure and health evidence;
- preserve deterministic behavior where promised;
- document explicit exclusions;
- include automated tests where code is introduced;
- pass CI;
- receive human review before merge.
