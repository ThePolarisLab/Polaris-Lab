# Hermes v0.8 Certification Framework

## Purpose

PGE-009.10 certifies Hermes as one cohesive governed subsystem. Certification is based on recorded evidence, not implementation confidence or milestone completion alone.

This document defines the reusable framework. Individual provider and end-to-end certification results will be recorded in later increments.

## Governing principles

1. **Evidence before status.** A criterion cannot be marked `passed` without reviewable evidence.
2. **Organization isolation fails closed.** Cross-organization access is a release-blocking failure.
3. **Provenance remains continuous.** Executive outputs must trace to governed evidence and source observations.
4. **Replay is deterministic.** Duplicate ingestion and recovery must not create inconsistent state.
5. **Secrets remain outside domain state.** Credentials must not appear in evidence, logs, projections, or query results.
6. **Athena respects the Hermes boundary.** Reasoning consumes governed Hermes contracts rather than provider SDKs.
7. **Human review completes certification.** Automation supplies evidence; it does not approve the release.

## Status model

Every certification criterion has exactly one status:

- `planned` — evidence has not yet been evaluated;
- `passed` — required evidence exists and satisfies the criterion;
- `failed` — evidence demonstrates that the criterion is not satisfied;
- `deferred` — work is intentionally postponed with an approved follow-up;
- `excluded` — the criterion is outside the release boundary and has a documented reason.

A critical or high-severity criterion may not be deferred or excluded without explicit architecture and human approval.

## Required metadata

Each criterion records:

- stable identifier;
- certification domain;
- testable title;
- accountable owner;
- severity;
- required evidence;
- current status;
- exclusion reason when applicable.

The machine-readable baseline is maintained in `tests/certification/certificationManifest.ts`. Automated tests protect its structure and required domain coverage.

## Certification domains

### Connector contract

Verify provider adapters conform to the provider-neutral connector contracts and declare supported capabilities accurately.

### Integration

Verify source observations become governed evidence envelopes through the connector runtime.

### Projection

Verify governed evidence projects deterministically into organization-scoped executive entities.

### Query

Verify executive queries preserve organization isolation, bounded pagination, filtering, and stable ordering.

### Traceability

Verify query results can be traced through evidence references to the original source observation.

### Integrity

Verify replay, duplicate ingestion, idempotency keys, ordering, and optimistic versions remain deterministic.

### Resilience

Verify partial failures, retries, restart, stale checkpoints, and checkpoint recovery are bounded and observable.

### Security

Verify secret boundaries, least privilege, tenant isolation, and negative serialization behavior.

### Athena compatibility

Verify Athena consumes Hermes outputs through governed contracts and cites supporting evidence without direct connector access.

### Operations

Verify health and failure signals are observable through safe operational contracts suitable for Mission Control.

## Evidence rules

Evidence should be reproducible and reviewable. Accepted evidence includes:

- automated test results;
- deterministic fixtures;
- GitHub Actions logs and artifacts;
- architecture or security review records;
- benchmark reports;
- source-to-output trace samples;
- explicit human approval recorded in the pull request or certification report.

Screenshots or informal statements alone are not sufficient for release-critical criteria.

## Release gates

Hermes v0.8 cannot be certified until:

- all required automated tests pass;
- CI is successful on the release commit;
- no unresolved critical or high-severity security finding remains;
- organization isolation fails closed across every integrated stage;
- provenance is demonstrated end to end;
- replay and duplicate ingestion are deterministic;
- Athena uses governed Hermes outputs only;
- documentation matches implementation;
- the certification report records every criterion as passed, failed, deferred, or excluded;
- human review approves the release baseline.

## Increment sequence

1. **PGE-009.10.1 — Framework:** manifest, validation, CI, and governance documentation.
2. **PGE-009.10.2 — Connector conformance:** Outlook, Motive, and QuickBooks contract suites.
3. **PGE-009.10.3 — End-to-end integration:** evidence, projection, query, and traceability.
4. **PGE-009.10.4 — Resilience and security:** recovery, failure injection, isolation, and secret boundaries.
5. **PGE-009.10.5 — Athena compatibility:** governed reasoning boundary and evidence-backed outputs.
6. **PGE-009.10.6 — Release certification:** consolidated report, final review, and Hermes v0.8 release decision.

## Explicit exclusions from this increment

PGE-009.10.1 does not claim that any production provider is certified. It establishes the framework used to evaluate later increments. Production credentials, live Mor Logistics data, autonomous financial actions, and autonomous email sending remain outside this framework baseline.
