# Hermes End-to-End Integration and Traceability Certification

## Milestone

PGE-009.10.3 — End-to-End Integration & Traceability

## Decision

Hermes is certified for the deterministic reference path from governed evidence envelopes through executive projection and organization-scoped query results.

This certification covers the merged provider-neutral contracts and the Outlook, Motive, and QuickBooks reference data shapes. It does not certify live provider credentials, external network availability, failure recovery, security review, or Athena compatibility; those remain separate certification increments.

## Certified path

```text
Source observation
  -> EvidenceEnvelope
  -> ExecutiveProjectionEngine
  -> Executive entity and EvidenceReference
  -> ExecutiveReadQueryRepository
  -> ExecutiveQueryEngine result
```

## Traceability requirements

A projected executive entity must retain enough information to identify its source without consulting connector-specific state:

- organization identifier;
- connector identifier;
- provider/resource type;
- source record identifier;
- source reference when available;
- observation timestamp;
- external system reference;
- entity version.

Query services must return the governed entity without stripping its evidence or external references.

## Certified properties

### Provenance preservation

Projection helpers convert each evidence envelope into an `EvidenceReference` and an `ExternalReference`. The certification suite verifies that connector ID, provider, source record ID, source URL, and observation time survive projection and query.

### Cross-connector coexistence

Outlook tasks and QuickBooks financial snapshots can be projected into the same organization-scoped executive repository while retaining independent evidence chains.

### Organization isolation

Queries are always executed with an organization context. Evidence projected for one organization is not visible from another organization context.

### Replay determinism

The projection engine tracks processed idempotency keys. Replaying identical evidence returns a skipped execution result and does not mutate the stored executive entity or increment its version.

### Stable query boundary

The certification uses the public Executive Query Engine rather than reading projection internals. This proves traceability survives the same boundary used by dashboards and downstream governed consumers.

## Automated evidence

- `tests/certification/endToEndTraceability.test.ts`
- `tests/hermes/ExecutiveProjectionEngine.test.ts`
- `tests/hermes/ExecutiveQueryEngine.test.ts`

## Manifest criteria satisfied

- HCF-002 — governed evidence envelopes participate in an integrated path;
- HCF-003 — evidence projects deterministically into executive entities;
- HCF-004 — executive queries preserve organization isolation and deterministic behavior;
- HCF-005 — executive results trace to source observations;
- HCF-006 — duplicate ingestion and replay remain idempotent.

## Explicit exclusions

The following are not claimed by this milestone:

- live Microsoft Graph, Motive, or QuickBooks API connectivity;
- durable restart and partial-failure recovery;
- complete secret-boundary and threat-model certification;
- Athena reasoning compatibility certification;
- production performance or scalability certification.

## Certification conclusion

PGE-009.10.3 passes for the deterministic, in-process Hermes reference architecture. The evidence-to-projection-to-query chain is traceable, organization-isolated, and replay-safe under the certified test conditions.
