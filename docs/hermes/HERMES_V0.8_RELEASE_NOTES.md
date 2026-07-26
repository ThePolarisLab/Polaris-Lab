# Hermes v0.8 Release Notes

**Release status:** Release candidate documentation

**Release decision:** Pending final CI evidence and explicit human approval

## Overview

Hermes v0.8 establishes the governed evidence and integration foundation for Polaris. It provides provider-neutral connector contracts, deterministic ingestion and projection, organization-scoped executive queries, source provenance, resilience controls, safe operational signals, and a governed compatibility boundary for Athena.

This release candidate consolidates the work delivered through PGE-009.1 to PGE-009.10.5. The final release decision is governed by PGE-009.10.6 and must not be inferred from this document alone.

## Included capabilities

### Provider-neutral connector foundation

- Shared connector contracts and lifecycle orchestration.
- Capability declaration and connector health contracts.
- Checkpoint-aware synchronization and deterministic replay behavior.

### Reference connectors

- Microsoft Outlook.
- Motive Fleet.
- QuickBooks Financial.

The reference connectors are certified against repository fixtures and governed contracts. Live production credentials and live customer data are outside the v0.8 certification boundary.

### Governed evidence

- Provenance-preserving evidence envelopes.
- Stable source references and deterministic idempotency.
- Secret-safe evidence, health, and failure serialization.
- Organization isolation across ingestion, projection, and query paths.

### Executive read model and query engine

- Deterministic projection of governed evidence into executive entities.
- Organization-scoped filtering, pagination, and stable ordering.
- Traceability from executive outputs back to source observations.

### Resilience and security

- Checkpoint recovery and stale-checkpoint handling.
- Replay suppression and duplicate-ingestion protection.
- Partial-failure handling and safe operational signals.
- Negative tests for organization isolation and secret leakage.

### Athena compatibility

- Athena consumes Hermes through the governed public executive contract boundary.
- Evidence references remain attached to deterministic reasoning outputs.
- Direct provider access from Athena is outside the approved architecture.

## Certification support

Hermes v0.8 includes:

- a machine-readable certification manifest;
- connector conformance suites;
- end-to-end integration and traceability tests;
- resilience and security verification;
- Athena compatibility certification;
- dedicated certification test execution through `npm run test:certification`;
- full release verification through `npm run verify:release`.

## Compatibility and upgrade guidance

Hermes v0.8 is a governed repository baseline rather than a production migration package. Consumers should integrate through the published Hermes contracts and must not depend directly on provider-specific adapter internals.

Before adopting the release baseline:

1. Run `npm ci` using the committed lockfile.
2. Run `npm run test:certification`.
3. Run `npm run verify:release`.
4. Review the consolidated certification report.
5. Record explicit human approval before creating a release tag.

## Known limitations and exclusions

The following are not certified as production capabilities in v0.8:

- live Mor Logistics data or production provider credentials;
- production-grade persistent storage;
- managed credential-vault adapters;
- autonomous financial actions;
- autonomous email sending;
- executive briefing composition beyond the certified Hermes-to-Athena contract;
- production deployment, uptime, and service-level commitments.

These exclusions are intentional and do not weaken the certified repository contracts. They require separate milestones, architecture review, tests, and human approval.

## Release governance

A Hermes v0.8 tag may be created only after:

- all required CI and automated tests pass on the release commit;
- no unresolved critical or high-severity certification failure remains;
- documentation is reconciled with the merged implementation;
- the consolidated certification report is complete; and
- an authorized human reviewer explicitly approves the release baseline.

## Related records

- `docs/hermes/HERMES_ROADMAP.md`
- `docs/hermes/HERMES_CERTIFICATION_FRAMEWORK.md`
- `docs/hermes/HERMES_V0.8_RELEASE_CERTIFICATION_REPORT.md`
- `docs/hermes/HERMES_V0.8_HUMAN_APPROVAL_CHECKLIST.md`
