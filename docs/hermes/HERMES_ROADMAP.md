# Hermes v0.8 Roadmap

## Program objective

Deliver a governed, provider-neutral integration and executive-intelligence foundation on Polaris Runtime without compromising provenance, tenant isolation, explainability, security, or human authority.

## Delivery sequence

### PGE-009.1 — Hermes Charter and Architecture

Deliverables:

- project charter;
- reference architecture;
- provider-neutral connector ADR;
- milestone roadmap;
- explicit completion and exclusion criteria.

Exit criteria:

- constitutional alignment is documented;
- dependency and human-approval boundaries are explicit;
- the first implementation increment is bounded.

### PGE-009.2 — Connector Contract Foundation

Deliverables:

- connector identity and capability contracts;
- synchronization request, checkpoint, and result contracts;
- connector health/readiness model;
- evidence-envelope contract;
- validation and immutability tests;
- public exports and engineering documentation.

Exit criteria:

- no vendor SDK dependency in the domain core;
- tenant, provenance, idempotency, and schema-version fields are mandatory;
- tests and CI pass.

### PGE-009.3 — Connector Orchestration Runtime

Deliverables:

- connector registry;
- synchronization worker integration;
- checkpoint handling;
- bounded retries, timeout, and cancellation;
- canonical connector lifecycle events;
- Runtime metrics, health, and Mission Control integration.

### PGE-009.4 — Evidence and Normalization Foundation

Deliverables:

- evidence ingestion service;
- duplicate control;
- source-reference persistence boundary;
- canonical normalized-record contracts;
- provenance-preserving mapping pipeline;
- tenant-safe correlation keys.

### PGE-009.5 — Microsoft 365 Outlook Reference Connector

Deliverables:

- least-privilege Outlook adapter;
- message and conversation synchronization;
- attachment metadata and evidence references;
- incremental checkpoints;
- rate-limit and partial-failure handling;
- fixture-driven contract tests.

No autonomous email sending is included.

### PGE-009.6 — Motive Reference Connector

Deliverables:

- vehicle, driver, location, utilization, and IFTA observations;
- incremental synchronization and source provenance;
- fleet-oriented normalization;
- operational health tests.

### PGE-009.7 — QuickBooks Online Reference Connector

Deliverables:

- customer, invoice, payment, expense, and account observations;
- accounting evidence provenance;
- incremental checkpoints and duplicate controls;
- finance-specific permission boundaries.

No autonomous posting or payment is included.

### PGE-009.8 — Executive Briefing Read Model

Deliverables:

- cross-system executive read model;
- freshness and confidence indicators;
- evidence-linked morning brief;
- exceptions, commitments, and action proposals;
- explicit uncertainty and stale-data handling.

### PGE-009.9 — Human Approval and Authorized Actions

Deliverables:

- proposed-action contract;
- approval record and audit trail;
- scoped execution adapters;
- dry-run and consequence preview;
- denial, expiry, and revocation behavior.

### PGE-009.10 — Hermes v0.8 Certification

Verification:

- architecture and ADR compliance;
- full automated test suite;
- security and tenant-boundary review;
- connector contract conformance;
- failure, retry, replay, and idempotency tests;
- evidence traceability from executive output to source;
- documentation and release-note synchronization;
- GitHub Actions success;
- tagged release only after human approval.

## Pull-request plan

The expected sequence begins with:

- PR #51 — Hermes Charter and Architecture;
- PR #52 — Connector Contract Foundation;
- PR #53 — Connector Orchestration Runtime.

Later PR numbering is indicative and may change if necessary maintenance or security increments intervene.

## Non-negotiable quality gates

Every increment must:

- preserve tenant isolation;
- avoid plaintext secrets;
- retain source provenance;
- define idempotency behavior;
- expose failure and health evidence;
- document explicit exclusions;
- include automated tests where code is introduced;
- pass CI;
- receive human review before merge.