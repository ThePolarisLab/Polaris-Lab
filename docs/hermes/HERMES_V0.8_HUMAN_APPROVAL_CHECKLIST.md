# Hermes v0.8 Human Approval Checklist

**Milestone:** PGE-009.10.6  
**Purpose:** Record the explicit human release decision required before a Hermes v0.8 tag is created.

> A successful automated workflow is evidence, not approval. Complete this checklist against the exact release commit.

## Release identity

- Release candidate version: `v0.8`
- Release commit SHA: ______________________________
- Review date: ____________________________________
- Reviewer name: __________________________________
- Reviewer role: __________________________________
- Pull request: ___________________________________
- CI/workflow evidence: ___________________________

## Automated verification

- [ ] Dependencies installed successfully with `npm ci`.
- [ ] `npm run test:certification` passed on the release commit.
- [ ] `npm run verify:release` passed on the release commit.
- [ ] Required GitHub Actions checks are successful.
- [ ] Test evidence is linked or attached to the release review.
- [ ] No test was disabled, skipped, or weakened solely to obtain a passing release result.

## Certification review

- [ ] Every required certification-manifest criterion has an allowed reviewed status.
- [ ] No critical finding remains unresolved.
- [ ] No high-severity finding remains unresolved without explicit architecture and human approval.
- [ ] Outlook reference connector conformance is verified.
- [ ] Motive reference connector conformance is verified.
- [ ] QuickBooks reference connector conformance is verified.
- [ ] End-to-end provenance and traceability are verified.
- [ ] Organization isolation fails closed across certified stages.
- [ ] Replay, duplicate ingestion, ordering, and idempotency remain deterministic.
- [ ] Checkpoint recovery and partial-failure behavior are bounded and observable.
- [ ] Credentials and secrets are absent from governed evidence, projections, queries, logs, and safe health outputs.
- [ ] Athena consumes Hermes through the governed public boundary and preserves evidence references.

## Documentation review

- [ ] Hermes roadmap matches the merged implementation and milestone state.
- [ ] Certification framework matches the implemented manifest and tests.
- [ ] Connector certification records are present and accurate.
- [ ] End-to-end traceability documentation is present and accurate.
- [ ] Resilience and security documentation is present and accurate.
- [ ] Athena compatibility certification is present and accurate.
- [ ] Hermes v0.8 release notes accurately describe capabilities and exclusions.
- [ ] Hermes v0.8 release certification report is complete.
- [ ] No document claims production readiness for an excluded capability.

## Scope and risk review

- [ ] Production credentials and live customer data are explicitly outside the certified baseline.
- [ ] Production persistence, vault adapters, deployments, and service-level commitments are not misrepresented as certified.
- [ ] Autonomous email, financial, and operational actions remain excluded.
- [ ] Every accepted medium- or low-severity finding has a documented owner, impact, and follow-up issue.
- [ ] The release does not introduce an undocumented breaking contract change.
- [ ] The reviewer understands the release limitations and accepts the residual risk.

## Release decision

Select exactly one:

- [ ] **APPROVED FOR TAG** — all mandatory gates are satisfied.
- [ ] **APPROVED WITH RECORDED FOLLOW-UP** — all mandatory gates are satisfied and only non-blocking findings remain.
- [ ] **REJECTED** — one or more mandatory gates are not satisfied.

### Decision rationale

______________________________________________________________________________

______________________________________________________________________________

______________________________________________________________________________

### Approved follow-up issues, if any

- ________________________________________________
- ________________________________________________
- ________________________________________________

## Sign-off

Reviewer signature/name: __________________________

Date: _____________________________________________

Release tag created by: ____________________________

Tag date: _________________________________________
